import io
import json
import logging
from pathlib import Path

from PIL import Image as PILImage

from ..config import MEMES_DIR
from .database import get_db_conn

logger = logging.getLogger(__name__)
SIMILARITY_FRAME_SAMPLES = 5


def sample_frame_indices(
    frame_count: int, sample_count: int = SIMILARITY_FRAME_SAMPLES
) -> list[int]:
    """Sample frame indices for similarity check."""
    safe_frame_count = max(1, frame_count)
    safe_sample_count = max(1, min(sample_count, safe_frame_count))

    if safe_frame_count == 1:
        return [0]
    if safe_sample_count == 1:
        return [safe_frame_count // 2]

    indices = set()
    for i in range(safe_sample_count):
        ratio = i / (safe_sample_count - 1)
        index = round((safe_frame_count - 1) * ratio)
        indices.add(index)

    return sorted(indices)


def calculate_dhash(frame: PILImage.Image) -> int:
    """Calculate difference hash (dhash) for a frame.

    Resizes image to 9x8, converts to grayscale, and compares adjacent pixels.
    Produces a 64-bit integer.
    """
    gray_img = frame.convert("L").resize((9, 8), PILImage.Resampling.BILINEAR)
    pixels = list(gray_img.getdata())

    dhash_val = 0
    for y in range(8):
        row_offset = y * 9
        for x in range(8):
            left = pixels[row_offset + x]
            right = pixels[row_offset + x + 1]
            if left > right:
                dhash_val |= 1 << (y * 8 + x)

    return dhash_val


def calculate_histogram(frame: PILImage.Image) -> list[float]:
    """Calculate normalized 3D RGB color histogram with 64 bins (4 bins per channel)."""
    rgb_img = frame.convert("RGB").resize((32, 32), PILImage.Resampling.BILINEAR)
    pixels = list(rgb_img.getdata())

    histogram = [0] * 64
    for r, g, b in pixels:
        r_bin = min(3, r // 64)
        g_bin = min(3, g // 64)
        b_bin = min(3, b // 64)
        bin_idx = r_bin * 16 + g_bin * 4 + b_bin
        histogram[bin_idx] += 1

    total = len(pixels) or 1
    return [count / total for count in histogram]


def extract_similarity_features(image_bytes: bytes) -> dict | None:
    """Extract similarity features from image bytes."""
    try:
        with PILImage.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            aspect_ratio = width / height if height > 0 else 0.0

            frame_count = (
                getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) or 1
            )
            frame_indices = sample_frame_indices(frame_count, SIMILARITY_FRAME_SAMPLES)

            frames = []
            for idx in frame_indices:
                try:
                    img.seek(idx)
                    frame_copy = img.copy()

                    dhash_val = calculate_dhash(frame_copy)
                    hist_val = calculate_histogram(frame_copy)

                    frames.append({"hash": dhash_val, "histogram": hist_val})
                except Exception as e:
                    logger.warning(f"Failed to process frame {idx}: {e}")

            if not frames:
                return None

            return {
                "width": width,
                "height": height,
                "aspect_ratio": aspect_ratio,
                "frame_count": frame_count,
                "frames": frames,
            }
    except Exception as e:
        logger.error(f"Failed to extract similarity features: {e}", exc_info=True)
        return None


def hamming_distance(h1: int, h2: int) -> int:
    """Compute Hamming distance between two binary hashes (integers)."""
    return (h1 ^ h2).bit_count()


def histogram_similarity(hist1: list[float], hist2: list[float]) -> float:
    """Compute histogram intersection similarity."""
    return sum(min(h1, h2) for h1, h2 in zip(hist1, hist2))


def calculate_frame_similarity(f1: dict, f2: dict) -> float:
    """Compute similarity between two frames."""
    h_dist = hamming_distance(f1["hash"], f2["hash"])
    h_sim = 1.0 - h_dist / 64.0
    hist_sim = histogram_similarity(f1["histogram"], f2["histogram"])
    return h_sim * 0.7 + hist_sim * 0.3


def calculate_frame_set_similarity(frames1: list[dict], frames2: list[dict]) -> float:
    """Compute symmetric set-based frame similarity (handles dynamic animation frames)."""
    if not frames1 or not frames2:
        return 0.0

    def match_one_way(f_src: list[dict], f_dst: list[dict]) -> float:
        scores = []
        for f1 in f_src:
            max_score = 0.0
            for f2 in f_dst:
                score = calculate_frame_similarity(f1, f2)
                if score > max_score:
                    max_score = score
            scores.append(max_score)
        return sum(scores) / len(scores) if scores else 0.0

    sim_1_to_2 = match_one_way(frames1, frames2)
    sim_2_to_1 = match_one_way(frames2, frames1)
    return (sim_1_to_2 + sim_2_to_1) / 2.0


def calculate_dimension_similarity(w1: int, h1: int, w2: int, h2: int) -> float:
    """Compute dimension/area similarity."""
    area1 = w1 * h1
    area2 = w2 * h2
    if area1 == 0 or area2 == 0:
        return 0.0
    return min(area1, area2) / max(area1, area2)


def calculate_similarity_score(features1: dict, features2: dict) -> float:
    """Calculate overall similarity score between two feature sets."""
    if not features1 or not features2:
        return 0.0

    frame_sim = calculate_frame_set_similarity(features1["frames"], features2["frames"])

    aspect_diff = abs(features1["aspect_ratio"] - features2["aspect_ratio"])
    aspect_sim = max(0.0, 1.0 - aspect_diff)

    return frame_sim * 0.8 + aspect_sim * 0.2


def check_image_similarity(
    image_bytes: bytes, threshold: float
) -> tuple[str, float] | None:
    """Check if the provided image is similar to any existing meme in the database.

    Returns:
    ---
        (matched_filename, similarity_score) if a match is found, else None.
    """
    new_features = extract_similarity_features(image_bytes)
    if not new_features:
        return None

    # Calculate dynamic max aspect ratio difference based on threshold to optimize query
    max_aspect_diff = (
        max(0.2, 1.0 - (threshold - 0.8) / 0.2) if threshold > 0.8 else 1.0
    )
    aspect_low = new_features["aspect_ratio"] - max_aspect_diff
    aspect_high = new_features["aspect_ratio"] + max_aspect_diff

    # Load matched features from the database
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT filename, width, height, aspect_ratio, frame_count, features_json
            FROM meme_similarity_features
            WHERE aspect_ratio BETWEEN ? AND ?
            """,
            (aspect_low, aspect_high),
        )
        rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to query similarity features from database: {e}")
        rows = []
    finally:
        conn.close()

    for row in rows:
        filename = row["filename"]
        try:
            existing_features = {
                "width": row["width"],
                "height": row["height"],
                "aspect_ratio": row["aspect_ratio"],
                "frame_count": row["frame_count"],
                "frames": json.loads(row["features_json"]),
            }
            score = calculate_similarity_score(new_features, existing_features)
            if score >= threshold:
                return filename, score
        except Exception as e:
            logger.warning(f"Failed to compare similarity with {filename}: {e}")

    return None


async def sync_similarity_features(sender) -> None:
    """Startup task to incrementally calculate missing similarity features for memes."""
    try:
        import asyncio

        from .database import get_db_conn

        # Ensure target table is initialized
        conn = get_db_conn()
        cursor = conn.cursor()

        # Get all registered memes
        cursor.execute("SELECT filename FROM memes")
        meme_rows = cursor.fetchall()

        # Get already computed features
        try:
            cursor.execute("SELECT filename FROM meme_similarity_features")
            cached_rows = cursor.fetchall()
        except Exception:
            cached_rows = []

        conn.close()

        all_memes = {row["filename"] for row in meme_rows}
        cached_memes = {row["filename"] for row in cached_rows}

        missing_memes = all_memes - cached_memes
        if not missing_memes:
            return

        logger.info(
            f"[meme_manager] Found {len(missing_memes)} memes missing similarity features. Starting background calculation..."
        )

        conn = get_db_conn()
        cursor = conn.cursor()

        for idx, filename in enumerate(missing_memes):
            # Yield control back to event loop to avoid blocking startup
            await asyncio.sleep(0.01)

            file_path = Path(MEMES_DIR) / filename
            if not file_path.exists() or not file_path.is_file():
                continue

            try:
                content = file_path.read_bytes()
                features = extract_similarity_features(content)
                if features:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO meme_similarity_features
                        (filename, width, height, aspect_ratio, frame_count, features_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            filename,
                            features["width"],
                            features["height"],
                            features["aspect_ratio"],
                            features["frame_count"],
                            json.dumps(features["frames"]),
                        ),
                    )
                    if idx > 0 and idx % 50 == 0:
                        conn.commit()
            except Exception as e:
                logger.warning(
                    f"Failed to calculate similarity features for {filename}: {e}"
                )

        conn.commit()
        conn.close()
        logger.info("[meme_manager] Similarity features background sync complete.")
    except Exception as e:
        logger.error(
            f"[meme_manager] Error during similarity features sync: {e}", exc_info=True
        )
