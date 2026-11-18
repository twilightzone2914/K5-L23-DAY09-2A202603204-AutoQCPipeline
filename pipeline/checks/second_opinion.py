"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    so_cfg = cfg["second_opinion"]
    conf = so_cfg["conf"]
    min_area_px = so_cfg["min_area_px"]
    fp_conf = so_cfg["fp_conf"]
    iou_missing = so_cfg["iou_missing"]
    iou_match = so_cfg["iou_match"]
    iou_loose = so_cfg["iou_loose"]

    issues = []
    for p in ds.image_files():
        stem = p.stem
        if stem not in preds:
            continue
        if not ds.label_path(stem).exists():
            continue

        size = ds.image_size(stem)
        if not size or size[0] <= 0 or size[1] <= 0:
            continue
        W, H = size

        # Đọc nhãn hợp lệ và giữ số dòng gốc
        raw_lines = ds.read_label_lines(stem)
        if raw_lines is None:
            continue

        valid_labels = []
        for line_no, text in raw_lines:
            try:
                c, x, y, w, h = parse_yolo_line(text)
                if 0 <= c < len(ds.classes) and w > 0 and h > 0:
                    valid_labels.append((line_no, c, (x, y, w, h)))
            except ValueError:
                continue

        img_preds = preds.get(stem, [])

        # 1. Dự đoán của model đủ độ tin cậy và kích thước
        model_p = [
            r for r in img_preds
            if r[1] >= conf and (r[4] * W) * (r[5] * H) >= min_area_px
        ]

        for r in model_p:
            p_cls = int(r[0])
            p_conf = float(r[1])
            p_box = (float(r[2]), float(r[3]), float(r[4]), float(r[5]))

            cands = []
            for line_no, l_cls, l_box in valid_labels:
                iou = iou_xywh(p_box, l_box)
                if iou >= iou_missing:
                    cands.append((iou, l_cls, line_no))

            if not cands:
                issues.append(
                    Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_MISSING",
                        stem,
                        f"model thấy lớp {p_cls} (conf {p_conf:.2f}) nhưng nhãn thiếu",
                        line=None,
                        extra={"conf": p_conf, "class": p_cls},
                    )
                )
            else:
                same_class_cands = [iou for iou, l_cls, _ in cands if l_cls == p_cls]
                if same_class_cands:
                    best_same_iou = max(same_class_cands)
                    if best_same_iou < iou_loose:
                        issues.append(
                            Issue(
                                "second_opinion",
                                WARN,
                                "POSSIBLE_LOOSE_BOX",
                                stem,
                                f"box lỏng: IoU {best_same_iou:.2f} < {iou_loose}",
                                line=None,
                                extra={"conf": p_conf, "iou": round(best_same_iou, 4), "class": p_cls},
                            )
                        )
                else:
                    diff_class_cands = [iou for iou, l_cls, _ in cands if l_cls != p_cls]
                    if diff_class_cands:
                        best_diff_iou = max(diff_class_cands)
                        if best_diff_iou >= iou_match:
                            issues.append(
                                Issue(
                                    "second_opinion",
                                    WARN,
                                    "POSSIBLE_WRONG_CLASS",
                                    stem,
                                    f"nghi ngờ sai lớp: model thấy {p_cls} (conf {p_conf:.2f}), IoU {best_diff_iou:.2f} >= {iou_match}",
                                    line=None,
                                    extra={"conf": p_conf, "iou": round(best_diff_iou, 4), "class": p_cls},
                                )
                            )

        # 2. Nhãn không khớp dự đoán nào (False Positive)
        fp_preds = [r for r in img_preds if r[1] >= fp_conf]
        for line_no, l_cls, l_box in valid_labels:
            matches = any(
                iou_xywh(l_box, (float(r[2]), float(r[3]), float(r[4]), float(r[5]))) >= iou_missing
                for r in fp_preds
            )
            if not matches:
                issues.append(
                    Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_FALSE_POS",
                        stem,
                        f"box dòng {line_no} không khớp dự đoán nào của model",
                        line=line_no,
                        extra={"conf": 0.0, "class": l_cls},
                    )
                )

    return issues
