import plotly.graph_objects as go
import json

# Data
years = [1, 2, 3, 4, 5]
labels = ["Year 1", "Year 2", "Year 3", "Year 4", "Year 5"]
revenue = [0, 1314, 2628, 3942, 5256]  # in Lakh ₹
ebitda = [0, 460, 920, 1380, 1840]     # in Lakh ₹

fig = go.Figure()

fig.add_bar(x=labels, y=revenue, name="Revenue (Lakh ₹)")
fig.add_bar(x=labels, y=ebitda, name="EBITDA (Lakh ₹)")

fig.update_layout(
    title={
        "text": "Projected revenue and EBITDA growth (Years 1-5)",
    },
    barmode="group",
    legend=dict(orientation='h', yanchor='bottom', y=1.05, xanchor='center', x=0.5)
)

fig.update_xaxes(title_text="Year")
fig.update_yaxes(title_text="Amount (Lakh ₹)")

fig.update_traces(cliponaxis=False)

# Save chart
file_name = "eonforge_revenue_ebitda.png"
fig.write_image(file_name)

meta = {
    "caption": "Projected revenue and EBITDA for Years 1-5",
    "description": "Grouped bar chart showing annual revenue and EBITDA in Lakh rupees from Year 1 to Year 5."
}
with open(file_name + ".meta.json", "w") as f:
    json.dump(meta, f)

file_name