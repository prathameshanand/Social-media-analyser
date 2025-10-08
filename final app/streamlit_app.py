#!/usr/bin/env python3
"""
Streamlit UI: Sequential Multiverse Feature Report
Includes robust V1/V2 dummy data rendering, debug tools, fallbacks,
renamed "Fake News Detection" and added "Crisis Detection & Early Warning (Dummy)".
"""
import streamlit as st
import json
import pandas as pd
from typing import Dict, Any
import traceback

# ----------------------------
# Dummy data blocks (editable)
# ----------------------------
DUMMY_V1_OUTPUT = """
{
  "multiverse_combined": {
    "executive_summary": "DUMMY V1 📊: The document analysis indicates strong support for Project Alpha, which shows high performance and positive stakeholder sentiment, despite a minor noted risk in resource allocation. This V1 analysis focuses on high-level sentiment and topic clustering.",
    "sentiment_analysis": {
      "positive": {"percentage": 75, "reasoning": "DUMMY: Focus on achieved success metrics and optimistic future projections."},
      "negative": {"percentage": 10, "reasoning": "DUMMY: Minor budget overrun noted in the Q2 report section."},
      "neutral": {"percentage": 15, "reasoning": "DUMMY: Procedural updates and routine reporting."}
    },
    "topics": {
      "Alpha Project Success": {"relevance_score": 0.9, "representative_snippets": ["Dummy Snippet 1: Alpha exceeded Q3 goals.", "Dummy Snippet 2: Resource allocation concerns are minor."]},
      "Resource Allocation": {"relevance_score": 0.45, "representative_snippets": ["Dummy Snippet 3: Q4 budget adjustment required."]}
    }
  }
}
"""

DUMMY_V2_OUTPUT = """
{
  "multiverse_combined": {
    "entity_recognition": [
      {"name": "DUMMY Corp", "type": "ORGANIZATION", "count": 15},
      {"name": "Dr. Beta", "type": "PERSON", "count": 8},
      {"name": "Project Omega", "type": "PROJECT", "count": 25}
    ],
    "relationship_extraction": [
      {"entity1": "DUMMY Corp", "relationship": "employs", "entity2": "Dr. Beta", "evidence": "HR report"},
      {"entity1": "Dr. Beta", "relationship": "manages", "entity2": "Project Omega", "evidence": "Project lead announcement"}
    ],
    "anomaly_detection": [
      {"section": "Budget", "description": "DUMMY: 150% variance from Q1 projections in the Beta team's travel expenses. Highly unusual.", "severity": "High"}
    ],
    "controversy_score": {
      "value": 0.65,
      "explanation": "DUMMY: Moderate internal disagreement over phasing out Project Omega, driven by conflicting reports from DUMMY Corp leadership."
    },
    "project_potential_claims": [
        {
            "claim": "The product will capture 40% of its target market within 18 months.",
            "status": "High Potential",
            "reason": "Independent market research aligns with internal forecasts due to zero direct competition.",
            "confidence": 0.95
        },
        {
            "claim": "A major funding round of $50M will close next quarter.",
            "status": "Confirmed",
            "reason": "Final term sheet signed by two leading VC firms, pending legal closure in Q4.",
            "confidence": 0.99
        },
        {
            "claim": "Revenue projections for next year are set to exceed original targets by 25%.",
            "status": "Likely",
            "reason": "Q3 performance shows 15% better retention than modeled, making the 25% goal highly achievable.",
            "confidence": 0.88
        },
        {
            "claim": "Project Alpha's core technology has filed a patent application.",
            "status": "True",
            "reason": "Official USPTO filing receipt is attached to the R&D memo.",
            "confidence": 1.00
        }
    ]
  }
}
"""

# ----------------------------
# Dummy analysis functions
# ----------------------------
@st.cache_data
def run_v1_analysis_dummy(json_path: str) -> Dict[str, Any]:
    st.info(f"✨ V1 Analysis running on {json_path} (Dummy Data)...")
    return json.loads(DUMMY_V1_OUTPUT)


@st.cache_data
def run_v2_analysis_dummy(json_path: str) -> Dict[str, Any]:
    st.info(f"🚀 V2 Analysis running on {json_path} (Dummy Data)...")
    return json.loads(DUMMY_V2_OUTPUT)


# ----------------------------
# V1 rendering
# ----------------------------
def render_v1_features(v1_data: Dict[str, Any]):
    v1_combined = v1_data.get('multiverse_combined', {})

    # 1. Executive Summary
    st.markdown("---")
    st.markdown("<h2 style='color: #2196F3;'>📰 1. Executive Summary</h2>", unsafe_allow_html=True)
    st.markdown(v1_combined.get('executive_summary', 'Summary data is missing.'))

    # 2. Sentiment Analysis (Graph + Reasons)
    st.markdown("---")
    st.markdown("<h2 style='color: #FF9800;'>😊 2. Sentiment Analysis</h2>", unsafe_allow_html=True)

    sentiment_raw = v1_combined.get('sentiment_analysis', {})
    sentiment_data = [
        {"Sentiment": key.capitalize(), "Percentage": float(val.get('percentage', 0)), "Reasoning": val.get('reasoning', 'No reason provided.')}
        for key, val in sentiment_raw.items() if isinstance(val, dict) and val.get('percentage') is not None
    ]

    if sentiment_data:
        st.markdown("### 📊 Sentiment Distribution")
        df_sentiment = pd.DataFrame(sentiment_data)
        st.bar_chart(df_sentiment.set_index('Sentiment')['Percentage'])

        st.markdown("### 📋 Sentiment Reasons")
        col1, col2, col3 = st.columns(3)
        for data in sentiment_data:
            sentiment_type = data['Sentiment'].lower()
            if sentiment_type == 'positive':
                col, icon, color = col1, "👍", "#4CAF50"
            elif sentiment_type == 'negative':
                col, icon, color = col2, "👎", "#F44336"
            else:
                col, icon, color = col3, "😐", "#9E9E9E"

            with col:
                st.markdown(f"#### {icon} {data['Sentiment']} ({data['Percentage']}%)")
                st.info(data['Reasoning'])
    else:
        st.warning("Sentiment analysis data is missing or malformed.")

    # 3. Key Topics (Graph + Details)
    st.markdown("---")
    st.markdown("<h2 style='color: #673AB7;'>🎯 3. Key Topics</h2>", unsafe_allow_html=True)
    topics_raw = v1_combined.get('topics', {})
    topics_data = [
        {"Topic": name, "Relevance Score": float(details.get('relevance_score', 0))}
        for name, details in topics_raw.items() if isinstance(details, dict) and details.get('relevance_score') is not None
    ]

    if topics_data:
        st.markdown("### 📈 Topic Relevance Chart")
        df_topics = pd.DataFrame(topics_data)
        df_topics['Relevance Percentage'] = df_topics['Relevance Score'] * 100
        st.bar_chart(df_topics.set_index('Topic')['Relevance Percentage'])

        st.markdown("### 📝 Topic Details")
        for name, details in topics_raw.items():
            relevance = details.get('relevance_score', 'N/A')
            snippets = details.get('representative_snippets', [])

            with st.expander(f"**{name}** (Relevance: {relevance})", expanded=False):
                if snippets:
                    st.markdown("**Representative Snippets:**")
                    for snippet in snippets:
                        st.code(snippet, language='text')
                else:
                    st.info("No representative snippets provided.")
    else:
        st.warning("Topic analysis data is missing or malformed.")


# ----------------------------
# V2 rendering with fallbacks + debug
# ----------------------------
def render_v2_features(v2_data: Dict[str, Any], v1_data: Dict[str, Any]):
    """Renders Controversy, Entity Recognition, Relationships, Anomaly, Fake News Detection,
    and Crisis Detection & Early Warning (dummy). Robust fallbacks and debug controls."""
    v2_combined = v2_data.get('multiverse_combined', {}) if isinstance(v2_data, dict) else {}
    # NOTE: data originally in 'project_potential_claims' will be displayed as Fake News claims
    fake_news_raw = v2_combined.get('project_potential_claims', [])

    # Debug tools in sidebar
    show_raw = st.sidebar.checkbox("Show raw V2 JSON (debug)", value=False)
    force_reload_from_dummy = st.sidebar.button("Force load claims from DUMMY_V2_OUTPUT")

    # Fallback: top-level key
    if not fake_news_raw and isinstance(v2_data, dict):
        top_level_pc = v2_data.get('project_potential_claims', [])
        if top_level_pc:
            fake_news_raw = top_level_pc

    # Fallback: parse global DUMMY_V2_OUTPUT
    if not fake_news_raw:
        try:
            dummy_raw = globals().get("DUMMY_V2_OUTPUT", None)
            if dummy_raw and isinstance(dummy_raw, str):
                parsed = json.loads(dummy_raw)
                pc = parsed.get('multiverse_combined', {}).get('project_potential_claims') \
                     or parsed.get('project_potential_claims')
                if pc:
                    fake_news_raw = pc
        except Exception as e:
            if show_raw:
                st.error("Error parsing DUMMY_V2_OUTPUT: " + str(e))
                st.text(traceback.format_exc())

    # Force reload if user pressed the button
    if force_reload_from_dummy:
        try:
            dummy_raw = globals().get("DUMMY_V2_OUTPUT", None)
            if dummy_raw:
                parsed = json.loads(dummy_raw)
                forced_pc = parsed.get('multiverse_combined', {}).get('project_potential_claims') \
                            or parsed.get('project_potential_claims')
                if forced_pc:
                    fake_news_raw = forced_pc
                    st.success("✅ Forced load succeeded from DUMMY_V2_OUTPUT")
                else:
                    st.warning("⚠️ Forced load: no 'project_potential_claims' found in DUMMY_V2_OUTPUT")
            else:
                st.warning("⚠️ DUMMY_V2_OUTPUT not found in globals.")
        except Exception as e:
            st.error(f"Forced load failed: {e}")
            if show_raw:
                st.text(traceback.format_exc())

    # If debug requested, show raw structures
    if show_raw:
        st.markdown("#### Raw v2_data (debug)")
        st.json(v2_data)
        if globals().get("DUMMY_V2_OUTPUT"):
            st.markdown("#### Raw DUMMY_V2_OUTPUT (debug)")
            try:
                st.json(json.loads(globals().get("DUMMY_V2_OUTPUT")))
            except Exception as e:
                st.text("Could not parse DUMMY_V2_OUTPUT: " + str(e))

    st.markdown("---")
    st.markdown("<h2 style='color: #009688;'>🔎 4. V2 Deep Dive Analysis (Features)</h2>", unsafe_allow_html=True)

    try:
        # Layout columns
        col_controversy, col_fake_news_graph = st.columns(2)

        # 4.1 Controversy Score
        with col_controversy:
            st.markdown("### ⚠️ Controversy Score")
            controversy = v2_combined.get('controversy_score', {})
            if controversy:
                try:
                    raw_score = controversy.get('value', 0.0)
                    score = float(raw_score) if raw_score is not None else 0.0
                    score = max(0.0, min(1.0, score))
                    explanation = controversy.get('explanation', 'N/A')
                    st.metric(label="Controversy Level", value=f"{score:.2f} (Max 1.0)")
                    st.progress(score)
                    st.caption("Controversy Progress")
                    st.markdown(f"**Reason:** {explanation}")
                except Exception:
                    st.error("Controversy score data is malformed.")
            else:
                st.info("No controversy score provided.")

        # 4.2 Fake News Detection (was Project Potential Claims)
        with col_fake_news_graph:
            st.markdown("### 📰 Fake News Detection (Claims & Status)")
            if fake_news_raw:
                try:
                    df_fake = pd.DataFrame(fake_news_raw)
                    if 'status' in df_fake.columns:
                        status_counts = df_fake['status'].fillna('Unknown').value_counts().rename_axis('Status').reset_index(name='Count')
                        st.bar_chart(status_counts.set_index('Status'))
                    else:
                        st.info("No 'status' field in claims to plot.")
                except Exception as e:
                    st.error(f"Error plotting Fake News graph: {e}")
                    if show_raw:
                        st.text(traceback.format_exc())
            else:
                st.error("No Fake News claims found. Tried: v2_data['multiverse_combined'], v2_data top-level, and DUMMY_V2_OUTPUT.")

        # Detailed Fake News Verification (cards) — dark style for readability
        st.markdown("---")
        st.markdown("### ✅ Detailed Fake News Verification")
        if fake_news_raw:
            for claim in fake_news_raw:
                status = claim.get('status', 'Unknown')
                # use emoji but always render dark card for readability
                if status in ("Confirmed", "True"):
                    icon = "✅"
                elif status in ("High Potential", "Likely"):
                    icon = "👍"
                else:
                    icon = "❓"

                # Dark themed card
                st.markdown(
                    f'''
                    <div style="
                        background-color: #000000;
                        color: #FFFFFF;
                        padding: 15px;
                        border-radius: 10px;
                        margin-bottom: 12px;
                        line-height: 1.6;
                        box-shadow: 0px 0px 8px rgba(255,255,255,0.12);
                    ">
                        <strong style="font-size:16px;">{icon} Claim:</strong> <em>{claim.get("claim", "N/A")}</em><br>
                        <strong>Status:</strong> <span style="color:#00E676;">{status}</span><br>
                        <strong>Reason:</strong> {claim.get("reason", "Verification reason missing.")}<br>
                        <strong>Confidence:</strong> {claim.get("confidence", "N/A")}
                    </div>
                    ''',
                    unsafe_allow_html=True
                )
        else:
            st.error("No Fake News claims were analyzed (Data is empty or key is wrong). Use the sidebar debug tools to inspect and force-load DUMMY_V2_OUTPUT.")

        # 4.3 Entity Recognition
        st.markdown("### 👥 Entities Recognized")
        entities = v2_combined.get('entity_recognition', [])
        if entities:
            df_entities = pd.DataFrame(entities)
            st.dataframe(df_entities, hide_index=True)
        else:
            st.info("No entities detected.")

        # 4.4 Relationship Extraction
        st.markdown("### 🔗 Relationship Extraction")
        relationships = v2_combined.get('relationship_extraction', [])
        if relationships:
            st.markdown("Key relationships identified:")
            for rel in relationships:
                st.write(f"- **{rel.get('entity1', 'Unknown')}** {rel.get('relationship', 'is related to')} **{rel.get('entity2', 'Unknown')}** (Evidence: {rel.get('evidence', 'N/A')})")
        else:
            st.info("No relationships detected.")

        # 4.5 Anomaly detection
        st.markdown("### 🚨 Anomaly Detection")
        anomalies = v2_combined.get('anomaly_detection', [])
        if anomalies:
            for a in anomalies:
                severity = a.get('severity', 'Low')
                st.error(f"**{severity} Anomaly** in **{a.get('section', 'Unknown Section')}**: {a.get('description', 'No description.')}")
        else:
            st.info("No anomalies detected.")

        # ----------------------------
        # 4.6 Crisis Detection & Early Warning (Dummy)
        # ----------------------------
        st.markdown("---")
        st.markdown("### 🚨🆕 Crisis Detection & Early Warning (Dummy)")
        # Heuristic risk signals:
        # - controversy score (0..1)
        # - number of 'High' severity anomalies
        # - negative sentiment percentage from V1
        try:
            controversy_val = float(v2_combined.get('controversy_score', {}).get('value', 0.0) or 0.0)
        except Exception:
            controversy_val = 0.0

        high_anomalies = 0
        for a in anomalies:
            try:
                if str(a.get('severity', '')).strip().lower() == 'high':
                    high_anomalies += 1
            except Exception:
                continue

        # negative sentiment
        neg_pct = 0.0
        try:
            v1_sentiment = v1_data.get('multiverse_combined', {}).get('sentiment_analysis', {})
            neg_pct = float(v1_sentiment.get('negative', {}).get('percentage', 0) or 0)
        except Exception:
            neg_pct = 0.0

        # simple risk score (weighted)
        # controversy_val in [0,1], high_anomalies scaled, neg_pct in [0,100]
        anomaly_score = min(1.0, high_anomalies * 0.35)  # 1 high anomaly -> 0.35
        neg_score = min(1.0, (neg_pct / 100.0) * 0.6)    # negative sentiment up to 0.6 weight
        risk_score = round(min(1.0, 0.4 * controversy_val + 0.4 * anomaly_score + 0.2 * neg_score), 3)

        # Determine severity bucket
        if risk_score >= 0.75:
            severity_label = "Severe"
            banner_text = "RED ALERT — Immediate attention recommended"
            st.error(f"**{banner_text}** (Risk score: {risk_score:.2f})")
        elif risk_score >= 0.45:
            severity_label = "High"
            banner_text = "High risk — Escalate and investigate"
            st.warning(f"**{banner_text}** (Risk score: {risk_score:.2f})")
        elif risk_score >= 0.20:
            severity_label = "Medium"
            banner_text = "Monitor closely — potential issue"
            st.info(f"**{banner_text}** (Risk score: {risk_score:.2f})")
        else:
            severity_label = "Low"
            banner_text = "Low risk — normal monitoring"
            st.success(f"**{banner_text}** (Risk score: {risk_score:.2f})")

        # Show computed signals for transparency
        st.markdown(
            f"""
            **Signals used (dummy):**
            - Controversy: {controversy_val:.2f}
            - High severity anomalies: {high_anomalies}
            - Negative sentiment (%): {neg_pct:.1f}
            - Computed risk score: {risk_score:.3f}  → **{severity_label}**
            """
        )

        # Suggested next steps (dummy guidance)
        st.markdown("**Suggested Next Steps (dummy):**")
        if severity_label in ("Severe", "High"):
            st.markdown(
                "- Immediately notify stakeholders via email/SMS.\n"
                "- Open an incident ticket and assign a response owner.\n"
                "- Pull raw source documents, communications, and related transcripts for manual review.\n"
                "- Run focused entity-level sentiment and topic drilldown on the last 72 hours of data."
            )
        elif severity_label == "Medium":
            st.markdown(
                "- Schedule an urgent review meeting with domain leads.\n"
                "- Increase monitoring frequency for the affected topics/entities.\n"
                "- Validate anomalies by checking source logs and financial records (if applicable)."
            )
        else:
            st.markdown(
                "- Continue normal monitoring.\n"
                "- Run weekly automated checks for controversy spikes and anomaly counts."
            )

    except Exception as top_e:
        st.error(f"An unexpected rendering error occurred in V2 features: {top_e}")
        if show_raw:
            st.text(traceback.format_exc())


# ----------------------------
# Main app
# ----------------------------
def main_streamlit_app():
    st.set_page_config(
        page_title="Sequential Feature Report",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.markdown("<h1 style='text-align: center; color: #2196F3;'>🤖 Sequential Multiverse Feature Report</h1>", unsafe_allow_html=True)

    dummy_path = "/path/to/dummy_input.json"

    st.sidebar.header("Execution Control")
    st.sidebar.markdown("Click the button to run the sequential analysis and generate the feature report.")
    st.sidebar.markdown("Debug: Show raw V2 JSON or force-load claims from dummy JSON.")

    if st.sidebar.button("Run Sequential Analysis ➡️ Generate Features"):
        # Execute dummy analyses
        v1_data = run_v1_analysis_dummy(dummy_path)
        v2_data = run_v2_analysis_dummy(dummy_path)

        st.markdown("---")
        st.markdown("<h2 style='color: #4CAF50;'>✅ Full Feature Report Generated!</h2>", unsafe_allow_html=True)

        # Render sections
        render_v1_features(v1_data)
        render_v2_features(v2_data, v1_data)

        # Finale
        st.balloons()


if __name__ == "__main__":
    main_streamlit_app()
