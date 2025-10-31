# mes_streamlit.py
# ----------------------------------------
# 목적:
# 1) 브라우저로 들어오면 기존처럼 화면(로그인/재고/출하)을 보여준다.
# 2) GPT가 아래 형태로 들어오면 JSON만 돌려준다. (화면 X)
#    - https://meschat.streamlit.app/?api=login-for-gpt&userKey=...&password=...
#    - https://meschat.streamlit.app/?api=inventory-for-gpt&session_id=...&itemCode=...
#    - https://meschat.streamlit.app/?api=shipments-for-gpt&session_id=...&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
# ----------------------------------------

import streamlit as st
import requests
import pandas as pd
from datetime import date, timedelta

st.set_page_config(
    page_title="QFactory MES Helper",
    layout="wide"
)

BASE_URL = "https://qf3.qfactory.biz:8000"
requests.packages.urllib3.disable_warnings()


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


def _common_headers():
    return {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://qf3.qfactory.biz",
        "Referer": "https://qf3.qfactory.biz/",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Streamlit-MES/1.0"
    }


def mes_login(user_key: str, password: str):
    url = f"{BASE_URL}/common/login/post-login"
    headers = _common_headers()
    payload = {
        "companyCode": "BWC40601",
        "userKey": user_key,
        "password": password,
        "languageCode": "KO"
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


def mes_inventory_fetch_raw(max_limit: int = 9999):
    if not st.session_state.logged_in:
        return False, "로그인 필요", None

    info = st.session_state.login_info
    url = f"{BASE_URL}/inv/stock-onhand-lot/detail-list"
    headers = _common_headers()
    payload = {
        "languageCode": info.get("languageCode", "KO"),
        "companyId": info.get("companyId", 100),
        "plantId": info.get("plantId", 11),
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


def filter_inventory_rows(rows, item_code, item_name, warehouse_code, lot_code):
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

    out = []
    for r in rows:
        if not match(r.get("itemCode", ""), item_code):
            continue
        if not match(r.get("itemName", ""), item_name):
            continue
        if not match(r.get("warehouseCode", ""), warehouse_code):
            continue
        if not match(r.get("lotCode", ""), lot_code):
            continue
        out.append(r)
    return out


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

    out = []
    for r in rows:
        if not match(r.get("itemCode", ""), item_code):
            continue
        if not match(r.get("lotCode", ""), lot_code):
            continue
        if not match(r.get("partnerCode", ""), partner_code):
            continue
        out.append(r)
    return out


# -----------------------------------------------------------------
# 1) 여기서 GPT용 API 모드 먼저 처리
# -----------------------------------------------------------------
# Streamlit 최신버전은 st.query_params, 구버전은 st.experimental_get_query_params
try:
    qp = st.query_params  # type: ignore
    qp = dict(qp)
except Exception:
    qp = st.experimental_get_query_params()

api_mode = qp.get("api", [None])[0] if qp else None

if api_mode:
    # 공통: 로그인 안 돼 있으면, login-for-gpt 말고는 에러
    if api_mode == "login-for-gpt":
        user_key = qp.get("userKey", [""])[0]
        password = qp.get("password", [""])[0]
        if not user_key or not password:
            st.json({"ok": False, "message": "userKey / password 둘 다 필요합니다."})
            st.stop()
        ok, data = mes_login(user_key, password)
        if ok:
            st.json({"ok": True, "session_id": st.session_state.session_id, "message": "login success"})
        else:
            st.json({"ok": False, "message": st.session_state.last_error or "login failed"})
        st.stop()

    elif api_mode == "inventory-for-gpt":
        session_id = qp.get("session_id", [""])[0]
        if not st.session_state.logged_in or session_id != st.session_state.session_id:
            st.json({"ok": False, "message": "로그인 필요 또는 세션 불일치"})
            st.stop()
        item_code = qp.get("itemCode", [""])[0]
        item_name = qp.get("itemName", [""])[0]
        warehouse_code = qp.get("warehouseCode", [""])[0]
        lot_code = qp.get("lotCode", [""])[0]

        ok, msg, rows = mes_inventory_fetch_raw(max_limit=9999)
        if not ok:
            st.json({"ok": False, "message": msg})
            st.stop()
        filtered = filter_inventory_rows(rows, item_code, item_name, warehouse_code, lot_code)
        st.json({"ok": True, "rows": filtered, "message": "OK", "total": len(filtered)})
        st.stop()

    elif api_mode == "shipments-for-gpt":
        session_id = qp.get("session_id", [""])[0]
        if not st.session_state.logged_in or session_id != st.session_state.session_id:
            st.json({"ok": False, "message": "로그인 필요 또는 세션 불일치"})
            st.stop()

        date_from = qp.get("date_from", [""])[0]
        date_to = qp.get("date_to", [""])[0]
        item_code = qp.get("itemCode", [""])[0]
        lot_code = qp.get("lotCode", [""])[0]
        partner_code = qp.get("partnerCode", [""])[0]

        if not date_from or not date_to:
            st.json({"ok": False, "message": "date_from / date_to 둘 다 필요합니다. 예) 2025-10-29"})
            st.stop()

        ok, msg, rows = mes_shipment_fetch_raw(date_from, date_to, max_limit=9999)
        if not ok:
            st.json({"ok": False, "message": msg})
            st.stop()
        filtered = filter_shipment_rows(rows, item_code, lot_code, partner_code)
        st.json({"ok": True, "rows": filtered, "message": "OK", "total": len(filtered)})
        st.stop()

    else:
        st.json({"ok": False, "message": f"알 수 없는 api 모드: {api_mode}"})
        st.stop()

# -----------------------------------------------------------------
# 2) 여기부터는 기존 사람용 화면
# -----------------------------------------------------------------

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
        st.code('companyCode = "BWC40601"\nlanguageCode = "KO"', language="text")

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
    st.subheader("재고관리 조회")

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
            st.caption("조건은 화면에서 필터합니다.")

        if st.button("재고 조회"):
            ok, msg, rows = mes_inventory_fetch_raw(max_limit=9999)
            if not ok:
                st.error(msg)
            else:
                total_cnt = len(rows)
                filtered = filter_inventory_rows(rows, item_code, item_name, warehouse_code, lot_code)
                if not filtered:
                    st.warning(f"데이터가 없습니다. (원본 {total_cnt}건)")
                else:
                    df = pd.DataFrame(filtered)
                    st.dataframe(df, use_container_width=True)
                    st.caption(f"원본 {total_cnt}건 중 조건에 맞는 {len(filtered)}건")

elif page == "출하관리":
    st.subheader("출하이력 조회")

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
            st.caption("날짜는 원격, 나머지는 화면에서 필터합니다.")

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
                if not filtered:
                    st.warning(f"데이터가 없습니다. (원본 {total_cnt}건)")
                else:
                    df = pd.DataFrame(filtered)
                    st.dataframe(df, use_container_width=True)
                    st.caption(f"원본 {total_cnt}건 중 조건에 맞는 {len(filtered)}건")

# 끝
