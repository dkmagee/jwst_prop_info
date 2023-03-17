#!/usr/bin/env python

import bs4
import requests
import datetime as dt
import pandas as pd
import streamlit as st
from awesome_table import AwesomeTable
from awesome_table.column import Column, ColumnDType
import xmltodict


def get_prop_info(pid):
    htmlurl = (
        f"https://www.stsci.edu/cgi-bin/get-proposal-info?id={pid}&observatory=JWST"
    )
    html_response = requests.get(htmlurl)
    html_data = bs4.BeautifulSoup(html_response.text, "html.parser")
    ps = html_data.find_all("p")
    prop_info = {}
    if ps:
        prop_info["pi"] = ps[0].contents[1].strip()
        prop_info["pi_inst"] = ps[0].contents[5].strip()
        prop_info["title"] = ps[1].contents[1].strip()
        prop_info["cycle"] = int(ps[1].contents[5].strip())
        prop_info["allocation"] = float(ps[1].contents[9].strip().split()[0])
        try:
            prop_info["excl_time"] = int(ps[1].contents[-1].strip().split()[0])
        except IndexError:
            prop_info["excl_time"] = 0
        prop_info["ptype"] = html_data.find_all("h1")[0].contents[1].contents[0]
        links = html_data.find_all("a")
        prop_info["apt"] = links[9]
        prop_info["pdf"] = links[10]
    return prop_info


@st.cache_data
def get_visit_status(pid):
    xmlurl = f"https://www.stsci.edu/cgi-bin/get-visit-status?id={pid}&markupFormat=xml&observatory=JWST"
    xml_response = requests.get(xmlurl)
    visit_data = xmltodict.parse(xml_response.text)
    visits = []
    if isinstance(visit_data["visitStatusReport"]["visit"], list):
        visit_data_list = visit_data["visitStatusReport"]["visit"]
    else:
        visit_data_list = [visit_data["visitStatusReport"]["visit"]]
    for vd in visit_data_list:
        # observation, visit, status, target, configuration, hours, start_ut, end_ut, plan_window, repeat
        visit_dict = {}
        visit_dict["observation"] = vd["@observation"]
        visit_dict["visit"] = vd["@visit"]
        visit_dict["status"] = vd["status"]
        visit_dict["target"] = vd["target"]
        visit_dict["configuration"] = vd["configuration"]
        visit_dict["hours"] = vd["hours"]

        if "startTime" in vd:
            visit_dict["start_ut"] = vd["startTime"]
        else:
            visit_dict["start_ut"] = None

        if "endTime" in vd:
            visit_dict["end_ut"] = vd["endTime"]
        else:
            visit_dict["end_ut"] = None

        if "planWindow" in vd:
            if isinstance(vd["planWindow"], list):
                pws = ""
                for i in vd["planWindow"]:
                    pws += f"{i.split('(')[0]} "
                visit_dict["plan_window"] = pws
            else:
                visit_dict["plan_window"] = vd["planWindow"].split("(")[0]

        elif "longRangePlanStatus" in vd:
            visit_dict[
                "plan_window"
            ] = "Ready for long range planning, plan window not yet assigned"

        else:
            visit_dict["plan_window"] = None

        if "repeatedBy" in vd:
            rb = vd["repeatedBy"]
            visit_dict[
                "repeat"
            ] = f"Rescheduled by WOPR {rb['problemID']} as observation {rb['observation']} visit {rb['visit']} in this program"

        elif "repeatOf" in vd:
            ro = vd["repeatOf"]
            visit_dict[
                "repeat"
            ] = f"Repeat of observation {ro['observation']} visit(s) {ro['visit']} in this program by WOPR {ro['problemID']}"

        elif "approvedRepeat" in vd:
            ar = vd["approvedRepeat"]
            visit_dict[
                "repeat"
            ] = f"Repeat visit implementation pending by WOPR {ar['problemID']}"

        else:
            visit_dict["repeat"] = None

        visits.append(visit_dict)

    return pd.DataFrame(visits)


def make_md_link(link):
    url = f"https://www.stsci.edu/{link['href']}"
    name = link.contents[0]
    return f"[{name}]({url})"


def filter_df_by_status(status, df):
    df = df[df.status.notnull()]
    if status == "All":
        filtered_df = df
    else:
        filtered_df = df.loc[df["status"] == status]
    height = len(filtered_df) * 35 + 3
    return filtered_df, height


if "pid" not in st.session_state:
    st.session_state.pid = None

st.set_page_config(page_title="JWST Program Status", layout="wide")

with st.sidebar:
    st.write("# JWST Program Status")
    form = st.form(key="pid-form")
    pid = form.text_input("Enter Program ID")
    submit = form.form_submit_button("Submit")
    if submit:
        prop_info = get_prop_info(pid)
        if prop_info:
            st.session_state.pid = pid
        if not st.session_state.pid:
            st.write(f"Program not found.")

if st.session_state.pid:
    prop_info = get_prop_info(st.session_state.pid)
    status_df = get_visit_status(st.session_state.pid)
    status_df = status_df[status_df.status.notnull()]
    status_list = list(status_df["status"].drop_duplicates())
    st.title(prop_info["title"])

    with st.sidebar:
        st.header(f'{prop_info["ptype"]} {st.session_state.pid}')
        st.write(f'**PI**: {prop_info["pi"]}')
        st.write(f'**PI Institution**: {prop_info["pi_inst"]}')
        st.write(f'**Program Title**: {prop_info["title"]}')
        st.write(f'**Cycle**: {prop_info["cycle"]}')
        st.write(f'**Allocation**: {prop_info["allocation"]} hours')
        st.write(f'**Exclusive Period**: {prop_info["excl_time"]} months')
        st.subheader("Program Contents")
        st.write(make_md_link(prop_info["apt"]))
        st.write(make_md_link(prop_info["pdf"]))

    option = st.selectbox(
        "Select a program visit status:",
        (["All"] + status_list),
    )
    st.subheader(f"{option} Visits")

    filtered_df, df_height = filter_df_by_status(option, status_df)
    AwesomeTable(
        filtered_df,
        columns=[
            Column(name="observation", label="Observation ID"),
            Column(name="visit", label="Visit ID"),
            Column(name="status", label="Visit Status"),
            Column(name="target", label="Target"),
            Column(name="configuration", label="Science Instrument"),
            Column(name="hours", label="Hours"),
            Column(name="start_ut", label="Start Time (UTC)"),
            Column(name="end_ut", label="End Time (UTC)"),
            Column(name="plan_window", label="Plan Window/s"),
            Column(name="repeat", label="Repeat"),
        ],
        show_search=True,
        # show_order=True,
    )
