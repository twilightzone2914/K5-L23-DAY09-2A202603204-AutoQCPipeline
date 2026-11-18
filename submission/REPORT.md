# Báo cáo Day 09 — Mai Quang Khải, 2A202603204

## 1. Kết luận trước
Pipeline đưa ra kết luận: **Release** (mã thoát: `0`), đạt đầy đủ tiêu chuẩn chất lượng để phát hành bộ dữ liệu.
- **Dữ liệu đầu vào**: Nhận tổng cộng 224 ảnh từ `data/raw/images`.
- **Cửa nhận (Intake)**: Đã loại bỏ 21 ảnh không hợp lệ (2 ảnh hỏng `CORRUPT_IMAGE`, 1 ảnh nhỏ `IMAGE_TOO_SMALL`, 5 ảnh rò rỉ tập test `LEAK_TEST`, 7 ảnh trùng tuyệt đối `DUP_IMAGE_EXACT`, 6 ảnh trùng gần đúng `DUP_IMAGE_NEAR`).
- **Dữ liệu xuất (Export)**: Nhận vào pipeline và xuất thành công **203/224 ảnh** vào `submission/export/clean_v1`.
- **Lý do chính**: Sau quá trình sửa tự động và mô phỏng người duyệt (ngân sách 80 ảnh), toàn bộ **0 lỗi bắt buộc** (`severity: error`) còn tồn tại, và chỉ còn **16/203 ảnh có cảnh báo** (tỉ lệ cảnh báo $7.88\%$), thấp hơn ngưỡng chặn `warn_ratio_hold = 0.10` ($10.00\%$) quy định trong `configs/pipeline.yaml`.

---

## 2. Lỗi và phân việc

### Bảng phân loại lỗi (tổng hợp từ `02_error_list_v1.csv`):

| Mã lỗi | Số dòng | Số ảnh | Ai sửa (máy/người) | Vì sao |
|---|---:|---:|---|---|
| `CORRUPT_IMAGE` | 2 | 2 | Máy (Intake) | File ảnh rỗng hoặc hỏng cấu trúc header, không thể decode; máy loại bỏ ngay cửa vào. |
| `BAD_SIZE` | 3 | 3 | Máy (Intake) | Kích thước ảnh nhỏ hơn ngưỡng `min_side = 250px`; máy loại bỏ tự động. |
| `LEAK_TEST` | 5 | 5 | Máy (Intake) | Ảnh trùng khớp SHA256 hoặc pHash với tập `test`/`gold_val`; máy loại bỏ để chống rò rỉ dữ liệu đánh giá. |
| `DUP_IMAGE_EXACT` | 8 | 8 | Máy (Intake) | Trùng lặp SHA256 tuyệt đối với ảnh đã nhận; máy tự động giữ bản đầu tiên và loại các bản trùng. |
| `DUP_IMAGE_NEAR` | 3 | 3 | Máy (Intake) | Trùng lặp pHash gần đúng (khoảng cách $\le 8$); máy loại bỏ ảnh nén/downscale. |
| `BAD_CLASS_NAME` | 2 | 1 | Máy (Autofix) | Tên lớp viết sai quy ước hoa/thường (`Person`, `Bus`); máy tự động chuẩn hóa về lowercase trong `data.yaml`. |
| `BAD_CLASS_ID` | 6 | 6 | Máy (Autofix) | ID lớp ngoài phạm vi $0..3$ (như ID 99); máy tự động xóa dòng (drop line) vì không rõ ngữ nghĩa. |
| `BAD_FORMAT` | 3 | 3 | Máy (Autofix) | Dòng nhãn rác, sai số lượng trường hoặc chứa chuỗi ký tự; máy tự động xóa dòng. |
| `BOX_ZERO` | 4 | 4 | Máy (Autofix) | Box có chiều rộng hoặc chiều cao bằng 0; máy tự động xóa dòng. |
| `DUP_BOX` | 7 | 7 | Máy (Autofix) | Box trùng lặp tọa độ và lớp với box khác trong cùng ảnh; máy tự động xóa bản sao. |
| `BOX_OUT_OF_IMAGE` | 8 | 8 | Máy (Autofix) | Tọa độ box tràn viền ảnh nhẹ ($< 0.002$); máy tự động cắt xén (clip) tọa độ về đoạn $[0, 1]$. |
| `MISSING_LABEL_FILE` | 6 | 6 | Người (Queue) | Ảnh hoàn toàn thiếu file nhãn; máy không được tự bịa nhãn mà chuyển người gán (`needs_label`, ưu tiên 10.0). |
| `EMPTY_LABEL` | 12 | 12 | Người (Queue) | File nhãn rỗng (hoặc sau khi xóa hết box rác); đưa vào hàng đợi cảnh báo để người xác nhận có sót vật thể không. |
| `BOX_TINY` | 6 | 4 | Người / Bỏ qua | Cạnh ngắn $< 12px$; cảnh báo kích thước quá bé so với độ phân giải trích xuất đặc trưng của YOLO. |
| `BOX_HUGE` | 3 | 3 | Người / Bỏ qua | Diện tích box chiếm $> 95\%$ ảnh; cảnh báo khả năng gán bao trùm toàn cảnh. |
| `CLASS_RARE` | 4 | 1 | Hệ thống | Lớp có tần suất xuất hiện quá ít trong lô; cảnh báo mất cân bằng dữ liệu. |
| `POSSIBLE_WRONG_CLASS` | 14 | 14 | Người (Queue) | Model giám định ($\text{conf} \ge 0.80$) dự đoán khác lớp với nhãn; người duyệt thẩm định và sửa lại lớp. |
| `POSSIBLE_MISSING` | 32 | 32 | Người (Queue) | Model giám định phát hiện vật thể rõ ràng nhưng nhãn không có; người duyệt kiểm tra và vẽ thêm box. |
| `POSSIBLE_LOOSE_BOX` | 12 | 12 | Người (Queue) | Box nhãn bị bao quá lỏng ($\text{IoU} < 0.50$ và diện tích gấp $\ge 1.4$ lần model); người duyệt nắn lại tọa độ. |
| `POSSIBLE_FALSE_POS` | 25 | 24 | Người (Queue) | Box nhãn không có dự đoán nào của model ($\text{conf} \ge 0.10$) hỗ trợ; người duyệt kiểm tra xem có phải box ảo. |

### Rationale hàng đợi duyệt `05_review_queue.csv` và hiệu quả ngân sách:
- **Nguyên lý xếp hàng đầu**:
  - `img_0020` đứng đầu danh sách với độ ưu tiên cao nhất ($11.524$) vì tích hợp cùng lúc 3 vấn đề: vừa có dòng lỗi đã xóa (`FIXED_DROP_LINE`), vừa bị thiếu nhãn (`POSSIBLE_MISSING`), vừa bị nghi nhầm lớp (`POSSIBLE_WRONG_CLASS`). Điểm ưu tiên được tính bằng tổng trọng số các lỗi trên ảnh.
  - Ngay sau đó là toàn bộ 6 ảnh thiếu file nhãn (`NEEDS_LABEL`: `img_0031`, `img_0053`, `img_0126`, `img_0135`, `img_0170`, `img_0219`) với độ ưu tiên cố định $10.0$. Đây là các lỗi bắt buộc (`MISSING_LABEL_FILE`) mà máy không thể tự khắc phục; nếu người không gán nhãn thì chắc chắn gate sẽ chặn (`Rework`). Thuật toán ưu tiên tối đa việc cứu các ảnh có lỗi bắt buộc này.
  - Tiếp theo là các ảnh có nhiều cảnh báo ngữ nghĩa kết hợp (`POSSIBLE_WRONG_CLASS`, `POSSIBLE_MISSING`, `POSSIBLE_FALSE_POS`).
- **Hiệu quả xử lý với ngân sách 80 ảnh**:
  - Toàn bộ 6/6 ảnh thiếu file nhãn bắt buộc đã được người duyệt gán nhãn bổ sung, giải quyết dứt điểm các lỗi chặn.
  - Về lỗi ngữ nghĩa:
    - `POSSIBLE_WRONG_CLASS`: Đã xem và sửa **13/14 lỗi** (giảm từ 14 xuống 1 trong V3).
    - `POSSIBLE_MISSING`: Đã xem và thêm nhãn cho **31/32 vật thể** bị thiếu (giảm từ 32 xuống 1 trong V3).
    - `POSSIBLE_LOOSE_BOX`: Đã xem và nắn lại **11/12 box** bị lỏng (giảm từ 12 xuống 1 trong V3).
    - `POSSIBLE_FALSE_POS`: Đã rà soát và xóa bớt **11 box ảo** (giảm từ 24 xuống 13 trong V3).
    - `EMPTY_LABEL`: Đã bổ sung nhãn cho **9/15 ảnh rỗng** (giảm từ 15 xuống 6 trong V3).
  - Tổng cộng người duyệt đã xử lý **65 lỗi ngữ nghĩa nghiêm trọng nhất**, giúp số ảnh còn cảnh báo giảm mạnh từ 102 xuống chỉ còn 16 ảnh ($7.88\%$), đưa lô dữ liệu về trạng thái an toàn đạt chuẩn phát hành.

---

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau trên tập calib) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **8** | DUP_IMAGE_NEAR:<br>1.00 / 0.50 / F1 0.67 → **1.00 / 0.67 / F1 0.80** | Trên tập calib, dist=16 có Recall cao hơn ($0.83$), nhưng khi chạy thực tế trên `data/raw`, dist=16 gây over-merge (bắt nhầm các ảnh đường phố khác nhau chụp cùng góc/thời tiết, vd `img_0008` vs `img_0011` khoảng cách 15, và kích hoạt `LEAK_TEST` giả). Ngưỡng dist=8 đạt Precision $1.00$ tuyệt đối trên `data/raw`, phát hiện chuẩn xác các ảnh nén/downscale đến 75% (`img_0076`, `img_0143`, `img_0223`) mà không xóa nhầm ảnh thật. |
| `second_opinion.conf` | 0.25 | **0.80** | WRONG_CLASS:<br>0.56 / 0.83 / F1 0.67 → **1.00 / 0.83 / F1 0.91**<br>MISSING:<br>0.50 / 1.00 / F1 0.67 → **0.67 / 0.75 / F1 0.71** | Ngưỡng 0.25 quá lỏng khiến model phụ sinh ra rất nhiều cảnh báo ảo (Precision chỉ $0.50 - 0.56$), làm hàng đợi người duyệt bị tràn ngập cảnh báo giả và người duyệt lãng phí ngân sách 80 ảnh. Ngưỡng 0.80 lọc sạch nhiễu của model, đạt Precision $1.00$ cho nhầm lớp, giúp hàng đợi người duyệt tập trung tối đa vào các lỗi gán nhãn thực sự có giá trị cao. |

### Điểm đánh lừa của calibration:
Tập calibration (`data/calib`) chỉ có 39 ảnh và được tạo bằng các phép biến dạng nhân tạo. Vì kích thước tập calib rất nhỏ, khoảng cách giữa các ảnh âm tính (negative pairs) rất lớn, khiến các ngưỡng lỏng như `phash_dist = 16` trông có vẻ an toàn trên báo cáo sweep (không có False Positive, F1 đạt 0.91). Tuy nhiên, trên dữ liệu thực tế (`data/raw` gồm 224 ảnh đường phố), phân bố ảnh thực tế dày đặc hơn: hai khung cảnh giao thông khác nhau chụp trên cùng một đoạn đường có thể có pHash distance chỉ 13–15 (ví dụ `img_0008` và `img_0011` có khoảng cách 15 dù là 2 ảnh chụp các xe hoàn toàn khác nhau). Nếu máy móc chọn ngưỡng theo F1 cao nhất của tập calib, pipeline sẽ xóa nhầm ảnh thật ở `intake` và gây báo động giả rò rỉ dữ liệu `LEAK_TEST`. Do đó, calibration luôn phải được kiểm chứng lại trên dữ liệu thật.

---

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

### (a) Bằng chứng cửa chặn (Gate Proof):
- Đã thực hiện kiểm chứng khả năng chặn của gate khi thiếu ngân sách duyệt bằng lệnh:
  ```bash
  .venv/bin/python -m pipeline.run --budget 0 --reports work/gate_test_rep --export-dir work/gate_test_exp
  ```
- **Kết quả thực nghiệm**:
  - Khi ngân sách duyệt bằng 0, không có người duyệt gán nhãn cho 6 ảnh thiếu nhãn (`NEEDS_LABEL`).
  - Ở vòng 3, 6 lỗi bắt buộc `MISSING_LABEL_FILE` vẫn còn nguyên trong `07_error_list_v3`.
  - Cửa chặn ghi nhận `n_errors = 6 > 0`, lập tức trả về kết luận: **`REWORK — còn 6 lỗi bắt buộc chưa xử lý`**.
  - Tiến trình kết thúc với mã thoát: **`20`** (`EXIT_CODE=20`).
  - Pipeline thông báo: `Bước 5/5 KHÔNG xuất: còn lỗi bắt buộc (Rework) — trả về bước 3`. Thư mục `work/gate_test_exp` **hoàn toàn không được tạo ra**.
  - Điều này chứng minh cửa chặn hoạt động hoàn toàn chính xác: kiên quyết không xuất bản dataset khi còn lỗi bắt buộc.

### (b) Điểm mù mà pipeline không bắt được ($\ge 2$ điểm mù):
1. **Bounding box bị lỏng hoặc lệch mức độ nhẹ ($0.50 \le \text{IoU} < 0.75$)**:
   - Ngưỡng kiểm tra box lỏng của pipeline yêu cầu $\text{IoU} < 0.50$ và diện tích gấp $\ge 1.4$ lần model. Các box gán nhãn bị lỏng vừa phải (ví dụ bao thừa 20–30% viền xe hoặc dính bóng mặt đường) vẫn đạt $\text{IoU} \approx 0.60$ so với model giám định, hoàn toàn lọt qua cổng kiểm tra mà không bị cảnh báo.
2. **Lỗi phân loại sai mà cả người gán lẫn model giám định đều mắc phải (Shared Bias)**:
   - Ở các trường hợp ranh giới mập mờ giữa `truck` (xe tải nhỏ/bán tải) và `car` (xe SUV đô thị), hoặc vật thể bị che khuất một phần trong bóng râm, nếu người gán nhãn nhầm là `car` và model YOLO giám định cũng nhận diện sai thành `car` (hoặc conf cho `truck` $< 0.80$), cơ chế second opinion sẽ không ghi nhận bất đồng, khiến nhãn sai sót lọt vào tập dữ liệu cuối cùng.

---

## 5. Train: raw vs clean (tùy chọn, chấm riêng)

**Chưa chạy.**
- **Lý do**: Môi trường local ban đầu chỉ cấu hình các thư viện phục vụ QC Pipeline theo `requirements.txt`, chưa có sẵn gói `torch` và `ultralytics` tương thích Python 3.14 trên GPU NVIDIA RTX 3050 Laptop (yêu cầu tải và biên dịch bộ CUDA wheels dung lượng lớn nhiều GB). Theo đúng hướng dẫn của đề bài ([GUIDE.md](file:///mnt/samsung/Project/aithucchien/K5-L23-DAY09-2A202603204-AutoQCPipeline/GUIDE.md) Bước 4 & [RUBRIC.md](file:///mnt/samsung/Project/aithucchien/K5-L23-DAY09-2A202603204-AutoQCPipeline/RUBRIC.md) Mục 5), phần train là hạng mục tùy chọn thực hiện riêng trên Colab T4 qua notebook `day09_train_compare.ipynb`, học viên báo cáo trung thực "chưa chạy" để tập trung tối đa cho tính toàn vẹn của AutoQC Pipeline và đạt chuẩn kiểm tra `make check-core`.

---

## 6. Quyết định và ghi chú AI

### (a) Quyết định cuối cùng:
- **Quyết định**: **Release**.
  - Pipeline kết luận Release, mã thoát `0`.
  - Toàn bộ 0 lỗi bắt buộc còn lại sau xử lý.
  - Tỉ lệ ảnh còn cảnh báo là 16/203 ảnh ($7.88\%$), thỏa mãn điều kiện $< 10.00\%$.
  - Bộ dữ liệu đã được xuất hoàn chỉnh tại `submission/export/clean_v1`.
- **Điều kiện để đổi quyết định**: Nếu yêu cầu dự án chuyển sang trạng thái kiểm soát nghiêm ngặt không chấp nhận bất kỳ box lỏng hoặc cảnh báo ảo nào, hoặc ngân sách duyệt bị cắt giảm xuống dưới 70 ảnh (khiến tỉ lệ cảnh báo chưa duyệt vượt quá $10\%$), kết luận sẽ chuyển thành **Hold** yêu cầu cấp thêm ngân sách duyệt người.

### (b) Ghi chú sử dụng AI:
- **Prompt chính**: "Xây dựng module `pipeline/checks/second_opinion.py` so sánh nhãn với model_preds theo đúng `docs/PROMPTING.md`, phát hiện `POSSIBLE_WRONG_CLASS`, `POSSIBLE_MISSING`, `POSSIBLE_LOOSE_BOX`, và `POSSIBLE_FALSE_POS` với các ngưỡng từ `configs/pipeline.yaml`."
- **Cách kiểm**: Viết unit test độc lập kiểm tra từng hàm so khớp (`tests/unit/test_second_opinion.py`), chạy `pytest`, và quét mã tĩnh đảm bảo không vi phạm quy tắc anti-cheat (không tham chiếu file test/calib/gold).
- **1 lần AI sai**: AI ban đầu áp dụng điều kiện diện tích `min_area_px` cho toàn bộ dự đoán của model khi kiểm tra `POSSIBLE_FALSE_POS`. Điều này dẫn đến việc bỏ qua cảnh báo false positive của nhãn đối với các vật thể nhỏ hơn `min_area_px` (bị unit test `test_false_positive_uses_fp_conf_and_ignores_min_area` bắt lỗi). Đã phát hiện và sửa để logic `POSSIBLE_FALSE_POS` chỉ lọc theo `conf >= fp_conf` mà không bị ràng buộc bởi `min_area_px`.

### (c) Thưởng +2 CVAT (đối chiếu bộ lọc box nhỏ):
- **Lọc `width < 20`**: Kiểm tra trên toàn bộ dữ liệu có **64 box** khớp bộ lọc này. Các box này chủ yếu là nhãn người (`person`) đứng ở cự ly xa, có chiều rộng hẹp (khoảng 14–19 px) nhưng chiều cao đạt 40–60 px (tỉ lệ khung hình mảnh dẻ 1:3 đến 1:4).
- **Đối chiếu với `BOX_TINY` của pipeline**: Pipeline sử dụng tiêu chí `min(w, h) < 12px`, chỉ gắn cảnh báo đúng **6 box** (`img_0026 box 6`, `img_0051 box 5`, `img_0069 box 2`, `img_0161 box 2, 3, 4`). Bộ lọc `width < 20` của CVAT quá gắt đối với người đi bộ, gây ra 58 cảnh báo giả; trong khi ngưỡng 12 px của pipeline hợp lý hơn vì chỉ lọc những box thực sự quá nhỏ không đủ đặc trưng nhận diện.
- **Thuộc tính `can_review`**: Trong CVAT, người gán nhãn bật `attr["can_review"] == true` khi gặp trường hợp khó (bị che khuất nặng, mờ nét hoặc phân vân giữa car/truck) để chuyển lên chuyên gia reviewer kiểm tra lại. Trong pipeline, vai trò này được tự động hóa thông qua cơ chế xếp hạng hàng đợi `05_review_queue.csv`, tự động chấm điểm ưu tiên các ảnh có bất đồng giữa nhãn và model giám định để phân bổ ngân sách người duyệt tối ưu.
