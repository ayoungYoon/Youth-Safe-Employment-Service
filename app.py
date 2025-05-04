from flask import Flask, request, render_template_string
import pandas as pd
import ast
import difflib

app = Flask(__name__)

# 데이터 로딩
df_jobs = pd.read_csv("jobs.csv", encoding="cp949")
df_jobs = df_jobs.rename(columns={"유형": "흥미유형", "대표직업": "직업목록"})

df_industry = pd.read_csv("시군구_산업별_취업자_11차__20250411111523.csv", encoding="cp949")
df_match = pd.read_csv("산업_유형별_추천직업_예시.csv", encoding="utf-8-sig")
df_youth = pd.read_csv("청소년_취업_직업군_통계.csv", encoding="utf-8-sig")

# 사용자 성향 해석
def infer_interest_type(user_input):
    user_input = user_input.lower()
    if any(word in user_input for word in ["현실", "실용", "기계", "움직", "신체", "도구", "활동"]):
        return "현실형 (R)"
    elif any(word in user_input for word in ["탐구", "논리", "분석", "호기심", "지식", "이론", "추리"]):
        return "탐구형 (I)"
    elif any(word in user_input for word in ["예술", "감성", "창의", "자유", "표현", "상상", "창작"]):
        return "예술형 (A)"
    elif any(word in user_input for word in ["사람", "공감", "상담", "도움", "친절", "소통", "봉사"]):
        return "사회형 (S)"
    elif any(word in user_input for word in ["주도", "리더", "설득", "도전", "목표", "승부", "기획"]):
        return "진취형 (E)"
    elif any(word in user_input for word in ["계획", "정리", "규칙", "체계", "서류", "문서", "안정"]):
        return "관습형 (C)"
    else:
        return None

# 지역 산업 top3
def get_top_industries(region_name, top_n=3):
    region_df = df_industry[df_industry["행정구역별"] == region_name]
    region_df = region_df[region_df["산업별"] != "계"]
    region_df["취업자수"] = pd.to_numeric(region_df["2024.1/2"], errors='coerce')
    region_df = region_df.dropna(subset=["취업자수"])
    sorted_df = region_df.sort_values(by="취업자수", ascending=False)
    return sorted_df["산업별"].head(top_n).tolist()

# 청소년 선호 직군
def get_top_youth_job_categories(df_youth, top_n=3):
    df_youth["청소년_합산"] = df_youth["2023_13-18세"].fillna(0) + df_youth["2023_19-24세"].fillna(0)
    top_jobs = df_youth.sort_values(by="청소년_합산", ascending=False).head(top_n)
    return top_jobs["직업군"].tolist()

# 추천 직업 추출
def get_recommended_jobs(industries, interest_type):
    matched_jobs = []

    for industry in industries:
        close_matches = difflib.get_close_matches(industry, df_match['산업'], n=1, cutoff=0.6)
        if close_matches:
            match_industry = close_matches[0]
            rows = df_match[(df_match["산업"] == match_industry) & (df_match["흥미유형"] == interest_type)]
            for _, row in rows.iterrows():
                try:
                    jobs_list = ast.literal_eval(row["추천직업"])
                    matched_jobs.extend(jobs_list)
                except Exception as e:
                    print(f"[⚠️ 오류] 추천직업 변환 실패: {row['추천직업']}, 이유: {e}")

    if not matched_jobs:
        job_row = df_jobs[df_jobs["흥미유형"] == interest_type]
        if not job_row.empty:
            try:
                job_list_str = job_row.iloc[0]["직업목록"]
                fallback_jobs = [job.strip() for job in job_list_str.split(",")]
                matched_jobs.extend(fallback_jobs)
            except Exception as e:
                print(f"[⚠️ fallback 실패] 직업 목록 파싱 중 오류: {e}")

    return list(set(matched_jobs))

# HTML 템플릿
html_template = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>AI 혼합 직업 추천기</title>
    <style>
        body { font-family: 'Noto Sans KR', sans-serif; background: #f4f6f8; padding: 40px; text-align: center; }
        form { background: #fff; display: inline-block; padding: 30px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        input, select, button { padding: 10px; margin: 10px; font-size: 16px; border-radius: 5px; border: 1px solid #ccc; }
        button { background: #3498db; color: #fff; cursor: pointer; }
        button:hover { background: #2980b9; }
        ul { list-style: none; padding: 0; }
        li { background: #fff; margin: 5px auto; padding: 10px 20px; border-radius: 5px; width: 60%; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    </style>
</head>
<body>
    <h1>🌟 AI 혼합 직업 추천기</h1>
    <form method="post">
        <div>
            <label>당신의 성향을 입력해주세요:</label><br>
            <input type="text" name="user_input" required>
        </div>
        <div>
            <label>거주하는 시군구를 입력해주세요 (예: 서울 종로구):</label><br>
            <input type="text" name="region" required>
        </div>
        <button type="submit">🔍 추천받기</button>
    </form>

    {% if result %}
        <h2>🧠 흥미유형: {{ result.type }}</h2>
        <h3>🏭 지역 산업 TOP3:</h3>
        <ul>{% for ind in result.industries %}<li>{{ ind }}</li>{% endfor %}</ul>

        <h3>🧒 청소년 선호 직군:</h3>
        <ul>{% for jobcat in result.youth_jobs %}<li>{{ jobcat }}</li>{% endfor %}</ul>

        <h3>💼 추천 직업 목록:</h3>
        <ul>{% for job in result.jobs %}<li>{{ job }}</li>{% endfor %}</ul>
    {% elif error %}
        <p style="color:red">{{ error }}</p>
    {% endif %}
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    result = None
    error = None
    if request.method == 'POST':
        user_input = request.form.get('user_input', '')
        user_region = request.form.get('region', '')

        user_type = infer_interest_type(user_input)
        if not user_type:
            error = "성향 문장에서 흥미유형을 파악할 수 없습니다."
        else:
            top_industries = get_top_industries(user_region)
            top_youth_jobs = get_top_youth_job_categories(df_youth)
            if not top_industries:
                error = f"'{user_region}'에 대한 산업 정보를 찾을 수 없습니다."
            else:
                recommended_jobs = get_recommended_jobs(top_industries, user_type)
                result = {
                    "type": user_type,
                    "industries": top_industries,
                    "youth_jobs": top_youth_jobs,
                    "jobs": recommended_jobs
                }

    return render_template_string(html_template, result=result, error=error)

if __name__ == '__main__':
    app.run(debug=True)
