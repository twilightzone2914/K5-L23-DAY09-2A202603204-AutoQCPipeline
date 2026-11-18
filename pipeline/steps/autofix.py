"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


def fix(ds, issues, cfg):
    error_issues = [i for i in issues if i.severity == ERROR]
    if not error_issues:
        return []

    fixes = []
    removed_images = set()

    # 1. Xoá ảnh hỏng, quá nhỏ, trùng lặp, hoặc rò rỉ
    remove_codes = {"CORRUPT_IMAGE", "BAD_SIZE", "DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST"}
    for i in error_issues:
        if i.code in remove_codes and i.image not in removed_images:
            removed_images.add(i.image)
            im_p = ds.image_path(i.image)
            if im_p and im_p.exists():
                im_p.unlink()
            lp = ds.label_path(i.image)
            if lp.exists():
                lp.unlink()
            ds._size_cache.pop(i.image, None)
            fixes.append({
                "image": i.image,
                "line": "",
                "action": "remove_image",
                "before": i.message,
                "after": "đã xoá ảnh và nhãn",
            })

    # 2. Đổi tên lớp trong data.yaml đúng quy chuẩn
    has_bad_class_name = any(i.code == "BAD_CLASS_NAME" for i in error_issues)
    if has_bad_class_name and ds.yaml_path.exists():
        old_data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        old_names = old_data.get("names", {})
        old_data["names"] = list(cfg["classes"])
        ds.yaml_path.write_text(yaml.safe_dump(old_data, allow_unicode=True), encoding="utf-8")
        fixes.append({
            "image": "data.yaml",
            "line": "",
            "action": "rename_classes",
            "before": str(old_names),
            "after": str(cfg["classes"]),
        })

    # 3. Ảnh thiếu file nhãn: không bịa nhãn, chuyển người gán
    for i in error_issues:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed_images:
            fixes.append({
                "image": i.image,
                "line": "",
                "action": "needs_label",
                "before": "(không có file)",
                "after": "chuyển người gán",
            })

    # 4. Sửa các lỗi dòng nhãn
    drop_line_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    line_issues = defaultdict(lambda: defaultdict(list))
    for i in error_issues:
        if i.image in removed_images or i.image == "data.yaml":
            continue
        if i.line is not None and i.code in (drop_line_codes | {"BOX_OUT_OF_IMAGE"}):
            line_issues[i.image][int(i.line)].append(i)

    for stem, line_map in line_issues.items():
        lp = ds.label_path(stem)
        if not lp.exists():
            continue
        raw_lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()

        actions = {}  # line_no -> ("drop", fix_dict) or ("clip", new_line_str, fix_dict)
        for line_no, iss_list in line_map.items():
            if line_no < 1 or line_no > len(raw_lines):
                continue
            line_text = raw_lines[line_no - 1]
            codes = {x.code for x in iss_list}

            # Xoá dòng thắng clip_box
            if codes & drop_line_codes:
                actions[line_no] = (
                    "drop",
                    {
                        "image": stem,
                        "line": line_no,
                        "action": "drop_line",
                        "before": line_text,
                        "after": "",
                    },
                )
            elif "BOX_OUT_OF_IMAGE" in codes:
                try:
                    c, x, y, w, h = parse_yolo_line(line_text)
                    x1 = x - w / 2
                    y1 = y - h / 2
                    x2 = x + w / 2
                    y2 = y + h / 2

                    cx1 = max(0.0, min(1.0, x1))
                    cy1 = max(0.0, min(1.0, y1))
                    cx2 = max(0.0, min(1.0, x2))
                    cy2 = max(0.0, min(1.0, y2))
                    new_w = cx2 - cx1
                    new_h = cy2 - cy1

                    if new_w <= 1e-9 or new_h <= 1e-9:
                        actions[line_no] = (
                            "drop",
                            {
                                "image": stem,
                                "line": line_no,
                                "action": "drop_line",
                                "before": line_text,
                                "after": "",
                            },
                        )
                    else:
                        new_cx = (cx1 + cx2) / 2
                        new_cy = (cy1 + cy2) / 2
                        new_line = f"{c} {new_cx:.6f} {new_cy:.6f} {new_w:.6f} {new_h:.6f}"
                        actions[line_no] = (
                            "clip",
                            new_line,
                            {
                                "image": stem,
                                "line": line_no,
                                "action": "clip_box",
                                "before": line_text,
                                "after": new_line,
                            },
                        )
                except ValueError:
                    actions[line_no] = (
                        "drop",
                        {
                            "image": stem,
                            "line": line_no,
                            "action": "drop_line",
                            "before": line_text,
                            "after": "",
                        },
                    )

        # Ghi lại file nhãn
        new_lines = []
        for idx, line_text in enumerate(raw_lines):
            l_no = idx + 1
            if l_no in actions:
                act = actions[l_no]
                if act[0] == "drop":
                    fixes.append(act[1])
                    continue
                elif act[0] == "clip":
                    new_lines.append(act[1])
                    fixes.append(act[2])
            else:
                new_lines.append(line_text)

        lp.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")

    return fixes
