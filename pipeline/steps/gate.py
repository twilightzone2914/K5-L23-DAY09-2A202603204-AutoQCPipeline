"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    valid_stems = set(image_stems)
    rev_set = set(reviewed) if reviewed else set()
    n_images = len(valid_stems)

    n_errors = sum(1 for i in issues if i.severity == ERROR)

    warn_images = {
        i.image for i in issues
        if i.severity == WARN and i.image in valid_stems and i.image not in rev_set
    }
    n_warn_images = len(warn_images)
    warn_ratio = round(n_warn_images / n_images, 4) if n_images > 0 else 0.0

    hold_ratio = cfg["gate"]["warn_ratio_hold"]

    reasons = []
    if n_errors > 0:
        decision = "Rework"
        reasons.append(f"còn {n_errors} lỗi bắt buộc chưa xử lý")
    elif warn_ratio >= hold_ratio:
        decision = "Hold"
        reasons.append(f"tỉ lệ ảnh còn cảnh báo {warn_ratio:.2%} >= ngưỡng giữ lại {hold_ratio:.2%} ({n_warn_images}/{n_images} ảnh)")
    else:
        decision = "Release"
        reasons.append(f"đạt yêu cầu phát hành (0 lỗi bắt buộc, {n_warn_images}/{n_images} ảnh có cảnh báo ({warn_ratio:.2%}) < {hold_ratio:.2%})")

    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": n_warn_images,
        "n_images": n_images,
        "warn_ratio": warn_ratio,
        "reasons": reasons,
    }
