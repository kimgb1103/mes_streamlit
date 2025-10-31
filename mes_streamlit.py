# mes_streamlit.py
# ----------------------------------------
# 목적:
# 1) MES 로그인 (https://qf3.qfactory.biz:8000/common/login/post-login)
# 2) 재고관리 조회 (https://qf3.qfactory.biz:8000/inv/stock-onhand-lot/detail-list)
# 3) 출하이력 조회 (https://qf3.qfactory.biz:8000/sal/shipping_history/shipment-result-list)
# 4) GPT가 이 URL만 때려서 로그인/조회할 수 있도록 한 파일로 구성
#
# 변경 요점 (사용자 요청):
# - 재고관리: 조회조건을 MES에 그대로 보내서 필터링하지 말고
#             → 먼저 넉넉하게 가져온 다음(Payload 기본값으로) → Streamlit에서 조건으로 필터
#             → 그래서 limit와 관계없이 "조건에 맞는 것만" 표로 보여주기
# - 출하관리: 위와 같은 방식으로 적용 (날짜만 원격 필터, 나머지는 로컬 필터)
# - 복붙할 수 있는 전체코드
# ----------------------------------------

import streamlit as st
import requests
import pandas as pd
from datetime import date, timedelta

# 스트림릿 기본 설정
st.set_page_config(
    page_title="QFactory MES Helper",
    layout="wide"
)

# MES 서버 기본 URL
BASE_URL = "https://qf3.qfactory.biz:8000"

# 인증서 경고 끄기 (개발/테스트용)
requests.packages.urllib3.disable_warnings()

# 세션 초기화 함수
def init_session_state():
    if "session" not in st.session_state:
        st.session_state.session = requests.Session()
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "login_info" not in st.session_state:
        st.session_state.login_info = {}
    if "last_error" not in st.session_state:
        st.session_state.last_error = ""
    if "session_id" not in st.session_state:
        st.session_state.session_id = None

init_session_state()

# 공통 헤더
def _common_headers():
    return {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://qf3.qfactory.biz",
        "Referer": "https://qf3.qfactory.biz/",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Streamlit-MES/1.0"
    }

# MES 로그인
def mes_login(user_key: str, password: str):
    url = f"{BASE_URL}/common/login/post-login"
    headers = _common_headers()
    payload = {
        "companyCode": "BWC40601",   # 고정
        "userKey": user_key,         # 사용자 입력
        "password": password,        # 사용자 입력
        "languageCode": "KO"         # 고정
    }

    sess: requests.Session = st.session_state.session
    try:
        resp = sess.post(url, headers=headers, json=payload, verify=False, timeout=10)
    except Exception as e:
        st.session_state.last_error = f"로그인 요청 실패: {e}"
        return False, None

    if resp.status_code != 200:
        st.session_state.last_error = f"로그인 실패(HTTP {resp.status_code}): {resp.text}"
        return False, None

    try:
        data = resp.json()
    except Exception:
        st.session_state.last_error = f"로그인 응답이 JSON이 아님: {resp.text[:200]}"
        return False, None

    if not data.get("success"):
        st.session_state.last_error = f"로그인 실패: {data}"
        return False, data

    st.session_state.logged_in = True
    st.session_state.login_info = {
        "userKey": user_key,
        "companyCode": data["userInfo"]["companyCode"],
        "companyId": data["orgInfo"]["orgCompanyId"],
        "plantId": data["orgInfo"]["plantId"],
        "plantCode": data["orgInfo"]["plantCode"],
        "languageCode": data["userInfo"]["languageCode"],
        "userName": data["userInfo"]["userName"],
    }

    if not st.session_state.session_id:
        st.session_state.session_id = f"mes-{user_key}"

    st.session_state.last_error = ""
    return True, data

# 재고 원본 조회 (원격에서 먼저 크게 1번만 가져옴)
def mes_inventory_fetch_raw(max_limit: int = 9999):
    """
    MES에서 재고를 먼저 넉넉하게 가져오는 함수.
    이후 조건 필터는 로컬(Python)에서 처리한다.
    """
    if not st.session_state.logged_in:
        return False, "로그인 필요", None

    info = st.session_state.login_info
    url = f"{BASE_URL}/inv/stock-onhand-lot/detail-list"
    headers = _common_headers()

    payload = {
        "languageCode": info.get("languageCode", "KO"),
        "companyId": info.get("companyId", 100),
        "plantId": info.get("plantId", 11),
        # 여기서부터는 필터를 비워서 "전체"를 가져오게 한다
        "itemCode": "",
        "itemName": "",
        "itemType": "",
        "projectCode": "",
        "projectName": "",
        "productGroup": "",
        "itemClass1": "",
        "itemClass2": "",
        "warehouseCode": "",
        "warehouseName": "",
        "warehouseLocationCode": "",
        "defectiveFlag": "Y",
        "itemClass3": "",
        "itemClass4": "",
        "effectiveDateFrom": "",
        "effectiveDateTo": "",
        "creationDateFrom": "",
        "creationDateTo": "",
        "lotStatus": "",
        "lotCode": "",
        "jobName": "",
        "partnerItem": "",
        "peopleName": "",
        "start": 1,
        "page": 1,
        "limit": str(max_limit),
    }

    sess: requests.Session = st.session_state.session
    try:
        resp = sess.post(url, headers=headers, json=payload, verify=False, timeout=15)
    except Exception as e:
        return False, f"재고조회 요청 실패: {e}", None

    if resp.status_code != 200:
        return False, f"재고조회 실패(HTTP {resp.status_code}): {resp.text[:200]}", None

    try:
        data = resp.json()
    except Exception:
        return False, f"재고조회 응답이 JSON이 아님: {resp.text[:200]}", None

    rows = data.get("data", {}).get("list", [])
    return True, "OK", rows

# 재고 로컬 필터링
def filter_inventory_rows(rows, item_code, item_name, warehouse_code, lot_code):
    """
    가져온 rows(list[dict])에서 사용자가 입력한 조건에 맞는 것만 필터링.
    부분일치, 대소문자 무시.
    """
    if not rows:
        return []

    item_code = (item_code or "").strip().lower()
    item_name = (item_name or "").strip().lower()
    warehouse_code = (warehouse_code or "").strip().lower()
    lot_code = (lot_code or "").strip().lower()

    def match(val, cond):
        if not cond:
            return True
        return cond in str(val).lower()

    filtered = []
    for r in rows:
        if not match(r.get("itemCode", ""), item_code):
            continue
        if not match(r.get("itemName", ""), item_name):
            continue
        if not match(r.get("warehouseCode", ""), warehouse_code):
            continue
        if not match(r.get("lotCode", ""), lot_code):
            continue
        filtered.append(r)

    return filtered

# 출하 원본 조회 (날짜만 서버로 보내고 나머지는 로컬 필터)
def mes_shipment_fetch_raw(date_from: str, date_to: str, max_limit: int = 9999):
    if not st.session_state.logged_in:
        return False, "로그인 필요", None

    info = st.session_state.login_info
    url = f"{BASE_URL}/sal/shipping_history/shipment-result-list"
    headers = _common_headers()

    payload = {
        "languageCode": info.get("languageCode", "KO"),
        "companyId": info.get("companyId", 100),
        "shipmentDateFrom": date_from,
        "shipmentDateTo": date_to,
        "plantCode": info.get("plantCode", "BW1"),
        "plantId": info.get("plantId", 11),
        # 여기도 검색조건은 비워서 서버에서 최대한 가져오게 한다
        "partnerCode": "",
        "partnerName": "",
        "shipmentNum": "",
        "orderNum": "",
        "lotCode": "",
        "itemCode": "",
        "itemName": "",
        "projectCode": "",
        "projectName": "",
        "shippingCheck": "Y",
        "start": 1,
        "page": 1,
        "limit": str(max_limit),
    }

    sess: requests.Session = st.session_state.session
    try:
        resp = sess.post(url, headers=headers, json=payload, verify=False, timeout=15)
    except Exception as e:
        return False, f"출하이력 요청 실패: {e}", None

    if resp.status_code != 200:
        return False, f"출하이력 실패(HTTP {resp.status_code}): {resp.text[:200]}", None

    try:
        data = resp.json()
    except Exception:
        return False, f"출하이력 응답이 JSON이 아님: {resp.text[:200]}", None

    rows = data.get("data", {}).get("list", [])
    return True, "OK", rows

# 출하 로컬 필터링 (재고와 동일 로직)
def filter_shipment_rows(rows, item_code, lot_code, partner_code):
    if not rows:
        return []

    item_code = (item_code or "").strip().lower()
    lot_code = (lot_code or "").strip().lower()
    partner_code = (partner_code or "").strip().lower()

    def match(val, cond):
        if not cond:
            return True
        return cond in str(val).lower()

    filtered = []
    for r in rows:
        if not match(r.get("itemCode", ""), item_code):
            continue
        if not match(r.get("lotCode", ""), lot_code):
            continue
        if not match(r.get("partnerCode", ""), partner_code):
            continue
        filtered.append(r)

    return filtered

# ----------------------------------------
# UI 시작
# ----------------------------------------

st.title("QFactory MES 연동 (Streamlit 버전)")

with st.sidebar:
    st.header("메뉴")
    page = st.radio("기능 선택", ["로그인", "재고관리", "출하관리"])
    st.markdown("---")
    if st.session_state.logged_in:
        st.success(
            f"로그인됨: {st.session_state.login_info.get('userName','')} ({st.session_state.login_info.get('userKey','')})"
        )
        st.caption(
            f"회사: {st.session_state.login_info.get('companyCode','')} / 공장: {st.session_state.login_info.get('plantCode','')}"
        )
        st.caption(f"session_id: {st.session_state.session_id}")
    else:
        st.warning("로그인 필요")

if page == "로그인":
    st.subheader("MES 로그인")

    col1, col2 = st.columns(2)
    with col1:
        user_key = st.text_input("MES ID (userKey)", value=st.session_state.login_info.get("userKey", ""), max_chars=50)
        password = st.text_input("MES 비밀번호", type="password")
    with col2:
        st.write("고정값")
        st.code(
            'companyCode = "BWC40601"\nlanguageCode = "KO"',
            language="text"
        )

    if st.button("로그인"):
        if not user_key or not password:
            st.error("ID와 비밀번호를 입력하세요.")
        else:
            ok, data = mes_login(user_key, password)
            if ok:
                st.success("로그인 성공")
                st.json(data)
            else:
                st.error("로그인 실패")
                if st.session_state.last_error:
                    st.error(st.session_state.last_error)

elif page == "재고관리":
    st.subheader("재고관리 조회 (/inv/stock-onhand-lot/detail-list)")

    if not st.session_state.logged_in:
        st.error("먼저 로그인부터 하세요.")
    else:
        with st.expander("조회조건"):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                item_code = st.text_input("품목코드(itemCode)", value="")
            with c2:
                item_name = st.text_input("품목명(itemName)", value="")
            with c3:
                warehouse_code = st.text_input("창고코드(warehouseCode)", value="")
            with c4:
                lot_code = st.text_input("LOT코드(lotCode)", value="")

            st.caption("조건을 입력해도 MES에 그대로 보내지 않고, 먼저 전체를 받아서 여기서 필터합니다.")

        if st.button("재고 조회"):
            # 1) 일단 MES에서 크게 가져오고
            ok, msg, rows = mes_inventory_fetch_raw(max_limit=9999)
            if not ok:
                st.error(msg)
            else:
                total_cnt = len(rows)
                # 2) 여기서 조건에 맞게 필터
                filtered = filter_inventory_rows(rows, item_code, item_name, warehouse_code, lot_code)
                filtered_cnt = len(filtered)

                if filtered_cnt == 0:
                    st.warning(f"데이터가 없습니다. (원본 {total_cnt}건 중 조건에 맞는 0건)")
                else:
                    df = pd.DataFrame(filtered)
                    st.dataframe(df, use_container_width=True)
                    st.caption(f"원본 {total_cnt}건 중 조건에 맞는 {filtered_cnt}건")

elif page == "출하관리":
    st.subheader("출하이력 조회 (/sal/shipping_history/shipment-result-list)")

    if not st.session_state.logged_in:
        st.error("먼저 로그인부터 하세요.")
    else:
        today = date.today()
        yesterday = today - timedelta(days=1)

        with st.expander("조회조건"):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                date_from = st.date_input("출하일자 From", value=yesterday)
            with c2:
                date_to = st.date_input("출하일자 To", value=today)
            with c3:
                item_code = st.text_input("품목코드(itemCode)", value="")
            with c4:
                lot_code = st.text_input("LOT코드(lotCode)", value="")
            partner_code = st.text_input("거래처코드(partnerCode)", value="")

            st.caption("날짜 범위만 MES에 보내고, 품목/LOT/거래처는 여기서 필터합니다.")

        if st.button("출하이력 조회"):
            ok, msg, rows = mes_shipment_fetch_raw(
                date_from=date_from.strftime("%Y-%m-%d"),
                date_to=date_to.strftime("%Y-%m-%d"),
                max_limit=9999,
            )
            if not ok:
                st.error(msg)
            else:
                total_cnt = len(rows)
                filtered = filter_shipment_rows(rows, item_code, lot_code, partner_code)
                filtered_cnt = len(filtered)

                if filtered_cnt == 0:
                    st.warning(f"데이터가 없습니다. (원본 {total_cnt}건 중 조건에 맞는 0건)")
                else:
                    df = pd.DataFrame(filtered)
                    st.dataframe(df, use_container_width=True)
                    st.caption(f"원본 {total_cnt}건 중 조건에 맞는 {filtered_cnt}건")

# 끝
