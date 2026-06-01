import json
import logging
from pathlib import Path

from quart import current_app, jsonify, request

from ....config import MEMES_DIR
from ...db.database import get_db_conn
from ...db.similarity import calculate_similarity_score
from .common import trigger_tag_vectorization

logger = logging.getLogger(__name__)


async def check_duplicates():
    """扫描所有表情包以查找重复的相似表情"""
    try:
        threshold = float(request.args.get("threshold", 0.85))
        logger.info(
            f"[meme_manager] Starting duplicate scan with threshold={threshold}"
        )

        conn = get_db_conn()
        cursor = conn.cursor()

        # Load all memes metadata
        cursor.execute("SELECT filename, emotions, personas FROM memes")
        meme_rows = cursor.fetchall()
        meme_meta = {
            row["filename"]: {
                "emotions": [e.strip() for e in row["emotions"].split(",")]
                if row["emotions"]
                else [],
                "personas": [p.strip() for p in row["personas"].split(",")]
                if row["personas"]
                else [],
            }
            for row in meme_rows
        }
        logger.info(f"[meme_manager] Loaded {len(meme_meta)} memes metadata entries.")

        # Load all similarity features
        cursor.execute(
            "SELECT filename, width, height, aspect_ratio, frame_count, features_json FROM meme_similarity_features"
        )
        rows = cursor.fetchall()
        conn.close()
        logger.info(f"[meme_manager] Loaded {len(rows)} similarity features from DB.")

        features_list = []
        for row in rows:
            filename = row["filename"]
            if filename not in meme_meta:
                continue
            try:
                features_list.append(
                    {
                        "filename": filename,
                        "width": row["width"],
                        "height": row["height"],
                        "aspect_ratio": row["aspect_ratio"],
                        "frame_count": row["frame_count"],
                        "frames": json.loads(row["features_json"]),
                        "meta": meme_meta[filename],
                    }
                )
            except Exception as e:
                logger.warning(
                    f"[meme_manager] Failed to load features for {filename}: {e}"
                )
                continue

        logger.info(
            f"[meme_manager] Loaded {len(features_list)} valid features for duplicate comparison."
        )

        # Group similar memes
        groups = []
        visited = set()

        for i, f1 in enumerate(features_list):
            if f1["filename"] in visited:
                continue

            group_memes = [f1]
            visited.add(f1["filename"])

            for f2 in features_list[i + 1 :]:
                if f2["filename"] in visited:
                    continue

                if abs(f1["aspect_ratio"] - f2["aspect_ratio"]) > 0.15:
                    continue

                score = calculate_similarity_score(f1, f2)
                if score >= threshold:
                    f2_copy = dict(f2)
                    f2_copy["similarity"] = score
                    group_memes.append(f2_copy)
                    visited.add(f2["filename"])

            if len(group_memes) > 1:
                f1_copy = dict(f1)
                f1_copy["similarity"] = 1.0
                group_memes[0] = f1_copy

                clean_memes = []
                for m in group_memes:
                    file_path = Path(MEMES_DIR) / m["filename"]
                    size_bytes = file_path.stat().st_size if file_path.exists() else 0
                    clean_memes.append(
                        {
                            "filename": m["filename"],
                            "emotions": m["meta"]["emotions"],
                            "personas": m["meta"]["personas"],
                            "similarity": m["similarity"],
                            "width": m.get("width", 0),
                            "height": m.get("height", 0),
                            "size_bytes": size_bytes,
                        }
                    )
                groups.append({"id": f"group_{len(groups) + 1}", "memes": clean_memes})

        logger.info(
            f"[meme_manager] Duplicate scan complete. Found {len(groups)} duplicate groups."
        )
        return jsonify({"status": "success", "groups": groups}), 200
    except Exception as e:
        logger.error(f"检查重复表情包失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


async def resolve_duplicates():
    """解析重复表情包：保留一部分，删除另外一部分"""
    try:
        data = await request.get_json()
        keeps = data.get("keeps", [])
        deletes = data.get("deletes", [])

        if not keeps or not deletes:
            return jsonify({"message": "keeps and deletes lists are required"}), 400

        conn = get_db_conn()
        cursor = conn.cursor()

        # 1. Delete the deleted memes from database and filesystem
        for filename in deletes:
            cursor.execute("DELETE FROM memes WHERE filename = ?", (filename,))
            cursor.execute(
                "DELETE FROM meme_similarity_features WHERE filename = ?",
                (filename,),
            )

            file_path = Path(MEMES_DIR) / filename
            if file_path.exists():
                file_path.unlink()

        conn.commit()
        conn.close()

        # Reload
        plugin_config = current_app.config.get("PLUGIN_CONFIG", {})
        category_manager = plugin_config.get("category_manager")
        if category_manager:
            category_manager.sync_with_filesystem()

        trigger_tag_vectorization()

        return jsonify({"status": "success", "message": "重复表情清理完成"}), 200
    except Exception as e:
        logger.error(f"清理重复表情包失败: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500
