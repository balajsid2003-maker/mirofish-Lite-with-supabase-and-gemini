"""
图谱相关API路由 — MiroFish Lite (Supabase backend)
"""

import traceback
from flask import request, jsonify

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.supabase_graph_builder import SupabaseGraphBuilderService
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus

logger = get_logger("mirofish.api")


def allowed_file(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[-1].lower()
    return ext in Config.ALLOWED_EXTENSIONS


# ── Project management ──────────────────────────────────────────────────────

@graph_bp.route("/project/<project_id>", methods=["GET"])
def get_project(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        return jsonify({"success": False, "error": f"项目不存在: {project_id}"}), 404
    return jsonify({"success": True, "data": project.to_dict()})


@graph_bp.route("/project/list", methods=["GET"])
def list_projects():
    limit = request.args.get("limit", 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    return jsonify({"success": True, "data": [p.to_dict() for p in projects], "count": len(projects)})


@graph_bp.route("/project/<project_id>", methods=["DELETE"])
def delete_project(project_id: str):
    success = ProjectManager.delete_project(project_id)
    if not success:
        return jsonify({"success": False, "error": f"项目不存在或删除失败: {project_id}"}), 404
    return jsonify({"success": True, "message": f"项目已删除: {project_id}"})


@graph_bp.route("/project/<project_id>/reset", methods=["POST"])
def reset_project(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        return jsonify({"success": False, "error": f"项目不存在: {project_id}"}), 404
    project.status = ProjectStatus.ONTOLOGY_GENERATED if project.ontology else ProjectStatus.CREATED
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)
    return jsonify({"success": True, "message": f"项目已重置: {project_id}", "data": project.to_dict()})


# ── Interface 1: Generate Ontology ──────────────────────────────────────────

@graph_bp.route("/ontology/generate", methods=["POST"])
def generate_ontology():
    """Upload documents and generate ontology definition."""
    try:
        logger.info("=== 开始生成本体定义 ===")
        simulation_requirement = request.form.get("simulation_requirement", "")
        project_name = request.form.get("project_name", "Unnamed Project")
        additional_context = request.form.get("additional_context", "")

        if not simulation_requirement:
            return jsonify({"success": False, "error": "请提供模拟需求描述 (simulation_requirement)"}), 400

        uploaded_files = request.files.getlist("files")
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({"success": False, "error": "请至少上传一个文档文件"}), 400

        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        logger.info("创建项目: %s", project.project_id)

        document_texts = []
        all_text = ""

        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                file_info = ProjectManager.save_file_to_project(project.project_id, file, file.filename)
                project.files.append({"filename": file_info["original_filename"], "size": file_info["size"]})
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"

        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({"success": False, "error": "没有成功处理任何文档，请检查文件格式"}), 400

        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info("文本提取完成，共 %d 字符", len(all_text))

        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context or None,
        )

        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", []),
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)

        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length,
            },
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ── Interface 2: Build Graph ─────────────────────────────────────────────────

@graph_bp.route("/build", methods=["POST"])
def build_graph():
    """Build Supabase knowledge graph from project documents."""
    try:
        logger.info("=== 开始构建图谱 ===")

        # Validate Supabase config
        errors = Config.validate()
        if errors:
            return jsonify({"success": False, "error": "配置错误: " + "; ".join(errors)}), 500

        data = request.get_json() or {}
        project_id = data.get("project_id")
        if not project_id:
            return jsonify({"success": False, "error": "请提供 project_id"}), 400

        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({"success": False, "error": f"项目不存在: {project_id}"}), 404

        force = data.get("force", False)

        if project.status == ProjectStatus.CREATED:
            return jsonify({"success": False, "error": "项目尚未生成本体，请先调用 /ontology/generate"}), 400

        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": "图谱正在构建中，请勿重复提交。如需强制重建，请添加 force: true",
                "task_id": project.graph_build_task_id,
            }), 400

        if force and project.status in [
            ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED
        ]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None

        graph_name = data.get("graph_name", project.name or "MiroFish Graph")
        chunk_size = data.get("chunk_size", project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get("chunk_overlap", project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)

        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap

        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({"success": False, "error": "未找到提取的文本内容"}), 400

        ontology = project.ontology
        if not ontology:
            return jsonify({"success": False, "error": "未找到本体定义"}), 400

        builder = SupabaseGraphBuilderService()
        task_id = builder.build_graph_async(
            text=text,
            ontology=ontology,
            graph_name=graph_name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        # Recover graph_id from task metadata
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        graph_id = (task.metadata or {}).get("graph_id", "") if task else ""

        project.graph_id = graph_id
        project.graph_build_task_id = task_id
        project.status = ProjectStatus.GRAPH_BUILDING
        ProjectManager.save_project(project)

        logger.info("图谱构建任务已启动: task_id=%s graph_id=%s", task_id, graph_id)
        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "graph_id": graph_id,
                "task_id": task_id,
                "message": "图谱构建任务已启动（Supabase），请通过 /task/{task_id} 查询进度",
            },
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ── Task queries ─────────────────────────────────────────────────────────────

@graph_bp.route("/task/<task_id>", methods=["GET"])
def get_task(task_id: str):
    task = TaskManager().get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": f"任务不存在: {task_id}"}), 404
    return jsonify({"success": True, "data": task.to_dict()})


@graph_bp.route("/tasks", methods=["GET"])
def list_tasks():
    tasks = TaskManager().list_tasks()
    return jsonify({"success": True, "data": [t.to_dict() for t in tasks], "count": len(tasks)})


# ── Graph data ───────────────────────────────────────────────────────────────

@graph_bp.route("/data/<graph_id>", methods=["GET"])
def get_graph_data(graph_id: str):
    try:
        builder = SupabaseGraphBuilderService()
        graph_data = builder.get_graph_data(graph_id)
        return jsonify({"success": True, "data": graph_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@graph_bp.route("/delete/<graph_id>", methods=["DELETE"])
def delete_graph(graph_id: str):
    try:
        builder = SupabaseGraphBuilderService()
        builder.delete_graph(graph_id)
        return jsonify({"success": True, "message": f"图谱已删除: {graph_id}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ── API usage stats ──────────────────────────────────────────────────────────

@graph_bp.route("/stats/api-usage", methods=["GET"])
def get_api_usage():
    """Return Gemini API call counts for monitoring."""
    from ..utils.gemini_service import GeminiService
    return jsonify({
        "success": True,
        "data": {
            "total_calls": GeminiService.get_call_count(),
            "daily_budget": Config.MAX_API_CALLS_PER_SIMULATION * 15,
            "per_simulation_budget": Config.MAX_API_CALLS_PER_SIMULATION,
        },
    })
