import streamlit as st
import json

@st.cache_data
def load_rules():
    with open("rules.json", "r", encoding="utf-8") as f:
        return json.load(f)

rules = load_rules()

class MilitaryEligibilityEngine:
    def __init__(self, rules):
        self.rules = rules
        self.facts = {}
        self.results = []
        self.triggered_rules = []

    def add_fact(self, key, value):
        if key not in self.facts or self.facts[key] != value:
            self.facts[key] = value
            return True
        return False

    def _check_condition(self, cond):
        if not cond:
            return True
        for key, val in cond.items():
            if key not in self.facts or self.facts[key] is None:
                return False
            fact_val = self.facts[key]
            if isinstance(val, dict):
                if fact_val is None: 
                    return False
                if "gt" in val and not (fact_val > val["gt"]): 
                    return False
                if "lt" in val and not (fact_val < val["lt"]): 
                    return False
                if "gte" in val and not (fact_val >= val["gte"]): 
                    return False
                if "lte" in val and not (fact_val <= val["lte"]): 
                    return False
                if "eq" in val and fact_val != val["eq"]: 
                    return False
                if "between" in val:
                    l, h = val["between"]
                    if not (l <= fact_val <= h): 
                        return False
                if "or" in val:  # THÊM HỖ TRỢ TOÁN TỬ OR
                    for sub_cond in val["or"]:
                        if self._check_condition({key: sub_cond}):
                            break
                    else:
                        return False
            elif isinstance(val, list):
                if fact_val not in val: 
                    return False
            elif fact_val != val:
                return False
        return True

    def _apply_result(self, rule):
        result = rule["result"]
        if isinstance(result, dict):
            for k, v in result.items():
                if v is not None:
                    self.add_fact(k, v)
        else:
            self.results.append({
                "ruleId": rule["ruleId"],
                "description": rule["description"],
                "result": result,
                "source": rule["source"]
            })

    def run(self):
        # Chạy tất cả rule nhiều lần cho đến khi không còn rule nào kích hoạt
        max_iterations = 10
        for _ in range(max_iterations):
            triggered_count = len(self.triggered_rules)
            for rule in self.rules:
                rid = rule["ruleId"]
                if rid not in [r["ruleId"] for r in self.triggered_rules]:
                    if self._check_condition(rule["condition"]):
                        self.triggered_rules.append(rule)
                        self._apply_result(rule)
            
            if len(self.triggered_rules) == triggered_count:
                break

        self._calculate_health_classification()

        self._check_main_eligibility_rules()

        return self.conclude()

    def _calculate_health_classification(self):
        score_keys = [
            "heightScore", "weightScore", "chestScore",
            "bmiScore", "eyeScore", "astigmatismEyeScore"
        ]
        scores = []
        for k in score_keys:
            if k in self.facts and isinstance(self.facts[k], int):
                v = self.facts[k]
                if k == "eyeScore":
                    adj = v
                    if self.facts.get("hasRefractiveSurgeryHistory"):
                        adj += 1
                    if self.facts.get("hasCorrectionGlasses"):
                        adj += 1
                    if adj > 6:
                        adj = 6
                    if adj != v:
                        self.add_fact("eyeScoreAdjusted", adj)
                    scores.append(adj)
                else:
                    scores.append(v)
        
        if scores:
            max_score = max(scores)
            self.add_fact("healthClassification", [str(max_score)])
            self.add_fact("health_type_display", f"Loại {max_score}")
            st.info(f"**Điểm sức khỏe:** {scores} → Loại {max_score}")

    def _check_main_eligibility_rules(self):
        """Kiểm tra các rule chính về điều kiện nhập ngũ sau khi đã có healthClassification"""
        
        health_ok = self.facts.get("healthClassification") in [["1"], ["2"], ["3"]]
        age_ok = self.facts.get("age", 0) >= 18
        edu_ok = self.facts.get("academicStandard", 0) >= 8
        student = self.facts.get("educationStatus") == "Đang học đại học/cao đẳng chính quy"

        existing_defer = any(("Tạm hoãn" in r["result"] or "tạm hoãn" in r["result"]) for r in self.results)
        existing_exempt = any(("Miễn" in r["result"] or "miễn" in r["result"]) for r in self.results)
        
        if health_ok and age_ok and student:
            self.results.append({
                "ruleId": 41,
                "description": "Đang học đại học/cao đẳng chính quy",
                "result": "Tạm hoãn nghĩa vụ quân sự",
                "source": "Luật Nghĩa vụ quân sự 2015, Điều 41"
            })
            return
        
        if existing_defer or existing_exempt:
            return

        if health_ok and age_ok and edu_ok and not student:
            self.results.append({
                "ruleId": 1,
                "description": "Nam giới sức khỏe loại 1,2,3; học vấn ≥ 8/12; tuổi ≥ 18",
                "result": "Đủ điều kiện nhập ngũ",
                "source": "Thông tư 148/2018/TT-BQP, Chương 2, Điều 4"
            })
            st.success("✅ Đã kích hoạt Rule 1: Đủ điều kiện nhập ngũ")
            return
        
        return

    def conclude(self):
        exempt = [r for r in self.results if "Miễn" in r["result"] or "miễn" in r["result"]]
        defer = [r for r in self.results if "Tạm hoãn" in r["result"] or "tạm hoãn" in r["result"]]
        eligible = [r for r in self.results if "Đủ điều kiện" in r["result"] or "đủ điều kiện" in r["result"]]

        if exempt:
            return {"final": "MIỄN NGHĨA VỤ QUÂN SỰ", "reasons": exempt}
        elif defer:
            return {"final": "TẠM HOÃN NGHĨA VỤ QUÂN SỰ", "reasons": defer}
        elif eligible:
            health_display = self.facts.get("health_type_display", "Chưa xác định")
            return {
                "final": "ĐỦ ĐIỀU KIỆN NHẬP NGŨ",
                "health_type": health_display,
                "reasons": eligible
            }
        else:
            return {"final": "CHƯA ĐỦ THÔNG TIN ĐỂ KẾT LUẬN", "reasons": []}
        """Kiểm tra các rule chính về điều kiện nhập ngũ sau khi đã có healthClassification"""
        if (self._check_condition({"gender": "Nam", "healthClassification": ["1", "2", "3"], "age": {"between": [18, 25]}}) and
            not self.facts.get("educationStatus") == "Đang học đại học/cao đẳng chính quy"):
            self.results.append({
                "ruleId": 1,
                "description": "Nam giới có sức khỏe loại 1,2,3 không học cao đẳng đại học",
                "result": "Đủ điều kiện nhập ngũ",
                "source": "Thông tư 148/2018/TT-BQP, Chương 2, Điều 4"
            })
        
        elif (self._check_condition({"gender": "Nam", "healthClassification": ["1", "2", "3"], "age": {"between": [18, 27]}}) and
              self.facts.get("educationStatus") == "Đang học đại học/cao đẳng chính quy"):
            self.results.append({
                "ruleId": 2,
                "description": "Nam giới có sức khỏe loại 1,2,3 học cao đẳng, đại học",
                "result": "Đủ điều kiện nhập ngũ",
                "source": "Thông tư 148/2018/TT-BQP, Chương 2, Điều 4"
            })

    def conclude(self):
        exempt = [r for r in self.results if "Miễn" in r["result"] or "miễn" in r["result"]]
        defer = [r for r in self.results if "Tạm hoãn" in r["result"] or "tạm hoãn" in r["result"]]
        eligible = [r for r in self.results if "Đủ điều kiện" in r["result"] or "đủ điều kiện" in r["result"]]

        if exempt:
            return {"final": "MIỄN NGHĨA VỤ QUÂN SỰ", "reasons": exempt}
        elif defer:
            return {"final": "TẠM HOÃN NGHĨA VỤ QUÂN SỰ", "reasons": defer}
        elif eligible:
            health_display = self.facts.get("health_type_display", "Chưa xác định")
            return {
                "final": "ĐỦ ĐIỀU KIỆN NHẬP NGŨ",
                "health_type": health_display,
                "reasons": eligible
            }
        else:
            return {"final": "CHƯA ĐỦ THÔNG TIN ĐỂ KẾT LUẬN", "reasons": []}

# ====================== GIAO DIỆN ======================
st.set_page_config(page_title="NVQS Checker", layout="centered")
st.title("ĐÁNH GIÁ NGHĨA VỤ QUÂN SỰ")
st.markdown("*Tự động suy luận theo Thông tư 148, 105, 68/TT-BQP*")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Thông tin cơ bản")
    age = st.number_input("Tuổi", 16, 60, 20)
    height = st.number_input("Chiều cao (cm)", 100.0, 220.0, 165.0)
    weight = st.number_input("Cân nặng (kg)", 30.0, 200.0, 60.0)
    chest = st.number_input("Vòng ngực (cm)", 50.0, 150.0, 85.0)
with col2:
    st.subheader("Thị lực")
    right_eye = st.selectbox("Mắt phải /10", options=list(range(0, 11)), index=10)
    left_eye = st.selectbox("Mắt trái /10", options=list(range(0, 11)), index=10)
    total_eye = right_eye + left_eye
    myopia = st.slider("Cận thị (Diop)", 0.0, 10.0, 0.0, 0.25)
    astigmatism = st.slider("Loạn thị (Diop)", 0.0, 5.0, 0.0, 0.25)
    has_surgery = st.checkbox("Đã phẫu thuật khúc xạ (LASIK, SMILE...)")
    has_correction = False
    if myopia > 0:
        has_correction = st.checkbox("Có chỉnh kính")

is_university_student = st.checkbox("Đang học đại học/cao đẳng chính quy")
academic_standard = None
if not is_university_student:
    academic_standard = st.number_input("Trình độ văn hóa (x/12)", min_value=1, max_value=12, value=8, step=1)

col3, col4 = st.columns(2)
with col3:
    sole_breadwinner = st.checkbox("Lao động duy nhất nuôi thân nhân")
    family_martyr = st.checkbox("Con/em ruột liệt sĩ")
    family_injured = st.checkbox("Con thương binh hạng 1")
with col4:
    family_chemical = st.checkbox("Con bệnh binh/độc da cam ≥81%")
    sibling_serving = st.checkbox("Anh/em ruột đang tại ngũ/CAND")
    resettlement = st.checkbox("Di dân/giãn dân 3 năm đầu")

diseases = st.multiselect("Bệnh lý nghiêm trọng (miễn NVQS)", [
    "Tâm thần", "Động Kinh", "Parkinson", "Mù một mắt", "Điếc", "HIV", "Nghiện ma túy"
])

bmi = round(weight / ((height/100)**2), 2)
st.info(f"**Chỉ số BMI:** {bmi}")

def safe_add(e, k, v):
    if v is not None and v != "":
        if isinstance(v, (int, float)):
            if v == 0 and ("diopter" in k or "eye" in k.lower()):
                e.add_fact(k, v)
            elif v > 0:  
                e.add_fact(k, v)
        else:
            e.add_fact(k, v)

if st.button("KIỂM TRA NGHĨA VỤ QUÂN SỰ", type="primary", use_container_width=True):
    engine = MilitaryEligibilityEngine(rules)

    safe_add(engine, "gender", "Nam")
    safe_add(engine, "age", age)
    safe_add(engine, "height_cm", height)
    safe_add(engine, "weight_kg", weight)
    safe_add(engine, "chest_cm", chest)
    safe_add(engine, "bmi", bmi)
    safe_add(engine, "right_eye_no_glasses", right_eye)
    safe_add(engine, "left_eye_no_glasses", left_eye)
    safe_add(engine, "total_eyes_no_glasses", total_eye)
    
    if myopia > 0: 
        safe_add(engine, "myopia_diopter", myopia)
        safe_add(engine, "myopiaEyeScore", myopia)  # Thêm cả myopiaEyeScore
        if has_correction:
            safe_add(engine, "hasCorrectionGlasses", True)
    
    if astigmatism > 0: 
        safe_add(engine, "astigmatism_diopter", astigmatism)
    
    if has_surgery: 
        safe_add(engine, "hasRefractiveSurgeryHistory", True)
    
    if academic_standard is not None:
        safe_add(engine, "academicStandard", academic_standard)
    if is_university_student:
        safe_add(engine, "educationStatus", "Đang học đại học/cao đẳng chính quy")
    
    if sole_breadwinner: 
        safe_add(engine, "isSoleBreadwinner", True)
        safe_add(engine, "dependentsUnableToWork", True)
    
    if family_martyr: 
        safe_add(engine, "familyRelation", "Con hoặc anh/em ruột liệt sĩ")
    
    if family_injured: 
        safe_add(engine, "familyRelation", "Con thương binh/liệt sĩ hạng 1")
    
    if family_chemical: 
        safe_add(engine, "familyRelation", "Con thương binh hạng 2/bệnh binh/người nhiễm chất độc da cam")
        safe_add(engine, "laborDecline", 81)
    
    if sibling_serving: 
        safe_add(engine, "familyRelation", "anh/chị ruột là hạ sĩ quan, binh sĩ tại ngũ, chiến sĩ thực hiện nghĩa vụ Công an nhân dân")
    
    if resettlement: 
        safe_add(engine, "isResettlementCase", True)
    
    if diseases: 
        safe_add(engine, "diseaseCodeInExclusionList", True)
        safe_add(engine, "relatedToHeroinAndHIV", "HIV" in diseases or "Nghiện ma túy" in diseases)

    result = engine.run()

    st.markdown("---")
    st.subheader("Chỉ số thể lực")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Chiều cao", f"{height} cm")
    c2.metric("Cân nặng", f"{weight} kg")
    c3.metric("BMI", f"{bmi}")
    c4.metric("Vòng ngực", f"{chest} cm")

    st.subheader("BMI")
    st.write(f"Chỉ số BMI: {bmi}")
    bmi_score = engine.facts.get("bmiScore")
    if isinstance(bmi_score, int):
        st.success(f"Kết luận BMI: Loại {bmi_score}")
    else:
        st.warning("Kết luận BMI: Chưa xác định")

    st.subheader("Thị lực")
    st.write(f"Mắt phải: {right_eye}/10")
    st.write(f"Mắt trái: {left_eye}/10")
    st.write(f"Tổng thị lực: {total_eye}/20")
    st.write(f"Cận thị: {myopia} Diop")
    st.write(f"Loạn thị: {astigmatism} Diop")
    if has_surgery:
        st.write("Đã phẫu thuật khúc xạ")
    if myopia > 0 and has_correction:
        st.write("Có chỉnh kính")
    eye_score = engine.facts.get("eyeScore")
    astig_score = engine.facts.get("astigmatismEyeScore")
    eye_adjusted = engine.facts.get("eyeScoreAdjusted")
    if isinstance(eye_score, int):
        st.success(f"Kết luận mắt: Loại {eye_score}")
    else:
        st.warning("Kết luận mắt: Chưa xác định")
    if isinstance(astig_score, int):
        st.info(f"Loạn thị: Loại {astig_score}")
    if isinstance(eye_adjusted, int):
        st.info(f"Kết luận mắt sau điều chỉnh: Loại {eye_adjusted}")
        
    st.subheader("Giải thích loại sức khỏe")
    health_display = result.get("health_type", engine.facts.get("health_type_display", "Chưa xác định"))
    hc_list = engine.facts.get("healthClassification")
    hc_int = None
    if isinstance(hc_list, list) and hc_list:
        try:
            hc_int = int(hc_list[0])
        except:
            hc_int = None
    derived = []
    eye_for_explain = eye_adjusted if isinstance(eye_adjusted, int) else eye_score
    if isinstance(eye_for_explain, int):
        derived.append(eye_for_explain)
    if isinstance(bmi_score, int):
        derived.append(bmi_score)
    if derived:
        dmax = max(derived)
        eye_txt = f"Loại {eye_for_explain}" if isinstance(eye_for_explain, int) else "Chưa xác định"
        bmi_txt = f"Loại {bmi_score}" if isinstance(bmi_score, int) else "Chưa xác định"
        st.write(f"Mắt: {eye_txt}, BMI: {bmi_txt}")
        st.info(f"Lấy mức cao nhất giữa mắt và BMI: Loại {dmax}")
        if isinstance(hc_int, int):
            if hc_int == dmax:
                st.success("Trùng với kết quả tổng hợp loại sức khỏe")
            else:
                st.warning(f"Kết quả tổng hợp hiện tại: Loại {hc_int} (có thể do chỉ số khác cao hơn)")
    else:
        st.warning("Chưa đủ dữ liệu mắt/BMI để giải thích")

    st.subheader("Loại sức khỏe")
    st.info(f"{health_display}")

    st.subheader("Kết quả nhập ngũ")
    final = result["final"]
    if "MIỄN" in final:
        st.error(f"**{final}**")
    elif "TẠM HOÃN" in final:
        st.warning(f"**{final}**")
    elif "ĐỦ" in final:
        st.success(f"**{final}**")
    else:
        st.info(f"**{final}**")

    if result.get("reasons"):
        st.subheader("Căn cứ pháp lý")
        for r in result["reasons"]:
            with st.expander(f"Luật {r['ruleId']}: {r['description']}"):
                st.write(f"**Kết quả:** {r['result']}")
                st.caption(f"**Nguồn:** {r['source']}")

    
