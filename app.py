"""
Streamlit UI for the Legal Document Generation & Evaluation Agent.

Run locally:   streamlit run app.py
Deployed:      Streamlit Community Cloud (see README)

If no ANTHROPIC_API_KEY is configured (env var or sidebar field), the app
runs in template-fallback mode automatically -- so the demo always produces
a full result, per the assignment's "pre-run demo mode" allowance.
"""
import os
import sys
import json

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import case_parser
import reference_parser
import generator
import pipeline

st.set_page_config(page_title="Affidavit in Reply — Generation & Evaluation Agent", layout="wide")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

st.title("⚖️ Legal Document Generation & Evaluation Agent")
st.caption("Affidavit in Reply — generates a new affidavit from case facts using a reference format, then evaluates its own output.")

#change this

with st.sidebar:
    st.header("Settings")
    provider_choice = st.selectbox(
        "LLM provider",
        ["Auto-detect", "Anthropic (Claude)", "Hugging Face", "Template fallback (no LLM)"],
    )
    if provider_choice == "Anthropic (Claude)":
        api_key_input = st.text_input("Anthropic API key", type="password")
        if api_key_input:
            os.environ["ANTHROPIC_API_KEY"] = api_key_input
        model = st.text_input("Model", value="claude-sonnet-5")
        provider = "anthropic"
    elif provider_choice == "Hugging Face":
        hf_token_input = st.text_input("Hugging Face token (HF_TOKEN)", type="password")
        if hf_token_input:
            os.environ["HF_TOKEN"] = hf_token_input
        model = st.text_input("Model", value="meta-llama/Llama-3.1-8B-Instruct",
                               help="Any instruction-tuned chat model your HF token can call via the Inference API.")
        provider = "huggingface"
    elif provider_choice == "Template fallback (no LLM)":
        model = None
        provider = "template"
    else:
        model = None
        provider = None  # auto-detect at generation time

    st.markdown("---")
    detected = generator.detect_provider() if provider is None else provider
    st.markdown(f"**Generation mode:** {detected or 'template fallback (nothing configured)'}")
    st.markdown("---")
    st.markdown("**Inputs used**")
    st.markdown("- `data/reference_affidavit.txt` — format reference\n"
                "- `data/case_information.json` — case facts\n"
                "- `data/format_rules.json` — extracted format rules")

tab_generate, tab_reference, tab_case = st.tabs(["Generate & Evaluate", "Reference Document", "Case Information"])

with tab_reference:
    st.subheader("Reference Affidavit (format source)")
    with open(os.path.join(DATA_DIR, "reference_affidavit.txt")) as f:
        ref_text = f.read()
    st.text_area("Reference text", ref_text, height=400)
    if st.button("Analyse structure"):
        structure = reference_parser.parse_reference_structure(ref_text)
        st.json(structure)

with tab_case:
    st.subheader("Case Information (input facts)")
    with open(os.path.join(DATA_DIR, "case_information.json")) as f:
        case_info = json.load(f)
    st.json(case_info)

with tab_generate:
    st.subheader("Run the pipeline")
    st.markdown(
        "Reference Document → Structure Analysis → Entity Extraction → Content Mapping "
        "→ Document Generation → Validation → Evaluation Report"
    )
    if st.button("▶ Generate Affidavit in Reply", type="primary"):
        with st.spinner("Running pipeline..."):
            result = pipeline.run_pipeline(provider=provider, model=model)

        st.success(f"Done. Generation mode: `{result.generated.generation_mode}`")

        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown("### Generated Document")
            with open(result.docx_path, "rb") as f:
                st.download_button("⬇ Download .docx", f, file_name="generated_affidavit.docx")
            st.markdown("**Body paragraphs**")
            for i, (para, move) in enumerate(zip(result.generated.paragraphs, result.generated.paragraph_moves), start=1):
                st.markdown(f"**{i}.** _{move}_  \n{para}")

        with col2:
            st.markdown("### Evaluation Report")
            with open(result.report_json) as f:
                report = json.load(f)
            st.metric("Overall Score", f"{report['overall_score']}/100")
            st.markdown("**Dimension scores**")
            st.table(report["dimension_scores"])
            st.markdown("**Issues detected**")
            if not report["issues"]:
                st.info("No issues detected.")
            else:
                for issue in report["issues"]:
                    st.markdown(f"- **[{issue['dimension']} / {issue['severity']}]** {issue['message']}  \n  _Source: {issue['source']}_")
            with open(result.report_md) as f:
                st.download_button("⬇ Download evaluation report (.md)", f.read(), file_name="evaluation_report.md")
            st.download_button("⬇ Download evaluation report (.json)", json.dumps(report, indent=2), file_name="evaluation_report.json")
    else:
        st.info("Click the button above to run the full pipeline on the sample case (Sunrise Housing Pvt. Ltd. v. State of Maharashtra & MMRDA).")
