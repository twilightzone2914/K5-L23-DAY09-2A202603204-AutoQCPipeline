"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    fmt_cfg = cfg["label_format"]
    overflow_tol = fmt_cfg["overflow_tol"]
    min_box_px = fmt_cfg["min_box_px"]
    max_box_frac = fmt_cfg["max_box_frac"]
    dup_box_iou = fmt_cfg["dup_box_iou"]

    issues = []
    for lf in ds.label_files():
        stem = lf.stem
        raw_lines = ds.read_label_lines(stem)
        if raw_lines is None:
            continue
        size = ds.image_size(stem)
        valid_boxes = []

        for line_no, text in raw_lines:
            try:
                c, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem, f"sai định dạng: {e}", line=line_no))
                continue

            if not (0 <= c < len(ds.classes)):
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"id lớp {c} ngoài 0..{len(ds.classes) - 1}", line=line_no, extra={"class_id": c}))
                continue

            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem, f"kích thước <= 0: w={w}, h={h}", line=line_no, extra={"w": w, "h": h}))
                continue

            # Kiểm tra tràn ảnh
            overflow = max(0.0, -(x - w / 2), -(y - h / 2), (x + w / 2) - 1.0, (y + h / 2) - 1.0)
            if overflow > overflow_tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ảnh {overflow:.4f} > {overflow_tol}", line=line_no, extra={"overflow": round(overflow, 6)}))

            # Kiểm tra trùng box cùng lớp với dòng trước đó
            is_dup = False
            for prev_c, prev_box, prev_line in valid_boxes:
                if c == prev_c and iou_xywh((x, y, w, h), prev_box) > dup_box_iou:
                    issues.append(Issue("label_format", ERROR, "DUP_BOX", stem, f"trùng box với dòng {prev_line}", line=line_no, extra={"dup_of": prev_line}))
                    is_dup = True
                    break
            valid_boxes.append((c, (x, y, w, h), line_no))

            # Cảnh báo box quá nhỏ hoặc quá lớn
            if size is not None:
                w_px = w * size[0]
                h_px = h * size[1]
                short_px = min(w_px, h_px)
                if short_px < min_box_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem, f"cạnh ngắn {short_px:.1f}px < {min_box_px}px", line=line_no, extra={"short_side_px": round(short_px, 2)}))

            if w * h > max_box_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem, f"diện tích box {w * h:.3f} > {max_box_frac}", line=line_no, extra={"area_frac": round(w * h, 4)}))

    return issues
