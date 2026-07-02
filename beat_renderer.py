"""
Beat Renderer (Playwright HTML/CSS Edition)
===========================================
Renders storyboard beat animations by compiling dynamic HTML/CSS templates,
rendering them inside a headless Chrome window via Playwright, and encoding to MP4.
Provides pixel-perfect CSS keyframes and transitions synced exactly to audio durations.
"""

import os
import sys
import logging
import glob
import re
import json
import subprocess
from playwright.sync_api import sync_playwright

logger = logging.getLogger("YoutubeAutomator")

# Keep the name MANIM_FPS to match video_editor.py imports
MANIM_FPS = 30

RENDER_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CODE_LINES = [
    "def solve(grid):",
    "    # Traverse row by row",
    "    for r in range(len(grid)):",
    "        for c in range(len(grid[0])):",
    "            if grid[r][c] == 'T':",
    "                return True",
    "    return False"
]

# ── Code Syntax Highlighter ──────────────────────────────────────────────────

def _highlight_code_line_html(line):
    line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # Simple regex tokenizer for Python code
    keywords = r'\b(def|for|in|if|return|elif|else|while|import|from|try|except|class|with|as|pass|and|or|not)\b'
    strings = r'(".*?"|\'.*?\')'
    numbers = r'\b(\d+)\b'
    operators = r'([=+\-*/<>!&|]+)'
    
    comment_parts = line.split('#', 1)
    code_part = comment_parts[0]
    comment_text = '#' + comment_parts[1] if len(comment_parts) > 1 else ''
    
    pattern = re.compile(
        f'(?P<str>{strings})|'
        f'(?P<kw>{keywords})|'
        f'(?P<num>{numbers})|'
        f'(?P<op>{operators})'
    )
    
    last_idx = 0
    html_out = ""
    for m in pattern.finditer(code_part):
        start, end = m.span()
        html_out += code_part[last_idx:start]
        
        tok_type = m.lastgroup
        tok_val = m.group(tok_type)
        if tok_type == 'str':
            html_out += f'<span class="code-str">{tok_val}</span>'
        elif tok_type == 'kw':
            html_out += f'<span class="code-kw">{tok_val}</span>'
        elif tok_type == 'num':
            html_out += f'<span class="code-num">{tok_val}</span>'
        elif tok_type == 'op':
            html_out += f'<span class="code-op">{tok_val}</span>'
            
        last_idx = end
    html_out += code_part[last_idx:]
    
    if comment_text:
        html_out += f'<span class="code-comment">{comment_text}</span>'
        
    return html_out

# ── Dynamic HTML Page Compiler ────────────────────────────────────────────────

def _generate_beat_html(visual_action: str, visual_data: dict) -> str:
    # Setup fallbacks
    title = visual_data.get("title", "DSA Concept").replace('"', '&quot;')
    subtitle = visual_data.get("subtitle", "").replace('"', '&quot;')
    text = visual_data.get("text", "Key Insight").replace('"', '&quot;')
    color_name = visual_data.get("color", "accent")
    
    # 1. Full-Screen Cards HTML
    card_html = ""
    
    if visual_action == "title_card":
        card_html = f"""
        <div class="title-card-container">
            <div class="chips">
                <div class="chip chip-indigo"></div>
                <div class="chip chip-emerald"></div>
                <div class="chip chip-rose"></div>
                <div class="chip chip-amber"></div>
                <div class="chip chip-purple"></div>
            </div>
            <h1 class="title-text">{title}</h1>
            <div class="title-bar"></div>
            <h2 class="subtitle-text">{subtitle}</h2>
        </div>
        """
    elif visual_action == "cta_card":
        channel = visual_data.get("channel", "this channel").replace('"', '&quot;')
        card_html = f"""
        <div class="cta-card-container">
            <div class="cta-box">
                <div class="bell-icon">🔔</div>
                <h1 class="cta-title">{text}</h1>
                <h2 class="cta-channel">@{channel}</h2>
                <div class="cta-footer">👍 Like  •  🔔 Subscribe  •  💬 Comment</div>
            </div>
        </div>
        """
    elif visual_action == "text_only":
        card_html = f"""
        <div class="text-card-container">
            <div class="text-box text-{color_name}">{text}</div>
        </div>
        """
    elif visual_action == "show_complexity":
        time_c = visual_data.get("time", "O(n)").replace('"', '&quot;')
        space = visual_data.get("space", "O(1)").replace('"', '&quot;')
        label = visual_data.get("label", "Algorithm").replace('"', '&quot;')
        card_html = f"""
        <div class="complexity-container">
            <h1 class="comp-title">{label} Complexity</h1>
            <div class="comp-card">
                <div class="comp-label">Time Complexity</div>
                <div class="comp-value val-time">{time_c}</div>
                <div class="comp-divider"></div>
                <div class="comp-label">Space Complexity</div>
                <div class="comp-value val-space">{space}</div>
            </div>
        </div>
        """
    elif visual_action == "show_comparison":
        a_val = visual_data.get("a_val", "O(n^2)").replace('"', '&quot;')
        b_val = visual_data.get("b_val", "O(n log n)").replace('"', '&quot;')
        a_label = visual_data.get("a_label", "Approach A").replace('"', '&quot;')
        b_label = visual_data.get("b_label", "Approach B").replace('"', '&quot;')
        winner = visual_data.get("winner", "b")
        card_html = f"""
        <div class="comparison-container">
            <h1 class="comp-title">Complexity Comparison</h1>
            <div class="comp-row">
                <div class="comp-box {'box-winner' if winner == 'a' else 'box-loser'}">
                    <div class="box-label">{a_label}</div>
                    <div class="box-value val-time">{a_val}</div>
                    {'<div class="winner-tag">✓ BETTER</div>' if winner == 'a' else ''}
                </div>
                <div class="vs-label">VS</div>
                <div class="comp-box {'box-winner' if winner == 'b' else 'box-loser'}">
                    <div class="box-label">{b_label}</div>
                    <div class="box-value val-space">{b_val}</div>
                    {'<div class="winner-tag">✓ BETTER</div>' if winner == 'b' else ''}
                </div>
            </div>
        </div>
        """
    elif visual_action == "icon_card":
        icon = visual_data.get("icon", "database").replace('"', '&quot;')
        body = visual_data.get("body", "").replace('"', '&quot;')
        # Build simple icons inside HTML
        icon_svg = {
            "database": '<path d="M 0,-30 A 30 15 0 1 1 0,30 A 30 15 0 1 1 0,-30 Z M -30,-10 L -30,10 A 30 15 0 0 0 30,10 L 30,-10 Z M -30,15 L -30,35 A 30 15 0 0 0 30,35 L 30,15 Z" fill="#6366F1"/>',
            "array": '<rect x="-45" y="-15" width="90" height="30" rx="6" fill="none" stroke="#6366F1" stroke-width="4"/><line x1="-15" y1="-15" x2="-15" y2="15" stroke="#6366F1" stroke-width="3"/><line x1="15" y1="-15" x2="15" y2="15" stroke="#6366F1" stroke-width="3"/>',
            "pointer": '<path d="M -30,30 L 20,-20 M 20,-20 L 5,-20 M 20,-20 L 20,-5" fill="none" stroke="#F59E0B" stroke-width="6" stroke-linecap="round"/>',
            "loop": '<path d="M 0,0 A 25 25 0 1 1 25,-10 M 25,-10 L 15,-18 M 25,-10 L 32,2" fill="none" stroke="#10B981" stroke-width="5" stroke-linecap="round"/>',
            "check": '<circle cx="0" cy="0" r="30" fill="#10B981"/><path d="M -12,-2 L -2,8 L 12,-8" fill="none" stroke="#FFF" stroke-width="6" stroke-linecap="round"/>'
        }.get(icon, '<circle cx="0" cy="0" r="30" fill="#6366F1"/>')
        
        card_html = f"""
        <div class="icon-card-container">
            <div class="icon-box border-{color_name}">
                <div class="icon-graphic">
                    <svg width="100" height="100" viewBox="-50 -50 100 100">{icon_svg}</svg>
                </div>
                <div class="icon-text-block">
                    <h1 class="icon-title">{title}</h1>
                    <p class="icon-body">{body}</p>
                </div>
            </div>
        </div>
        """
    elif visual_action == "bullet_list":
        items = visual_data.get("items", ["Step 1", "Step 2", "Step 3"])
        items_html = ""
        for idx, it in enumerate(items[:5]):
            items_html += f"""
            <div class="bullet-row" style="animation-delay: {0.3 + idx*0.25}s">
                <div class="bullet-num bg-{color_name}">{idx+1}</div>
                <div class="bullet-text">{it.replace('"', '&quot;')}</div>
            </div>
            """
        card_html = f"""
        <div class="bullet-list-container">
            <h1 class="bullet-title">{title}</h1>
            <div class="bullet-items">
                {items_html}
            </div>
        </div>
        """
    elif visual_action == "stat_callout":
        value = visual_data.get("value", "O(log n)").replace('"', '&quot;')
        label = visual_data.get("label", "Complexity").replace('"', '&quot;')
        context = visual_data.get("context", "").replace('"', '&quot;')
        card_html = f"""
        <div class="stat-card-container">
            <div class="stat-graphic anim-pulse-delay">
                <div class="stat-rings border-{color_name}">
                    <div class="stat-value">{value}</div>
                </div>
            </div>
            <div class="stat-text-block">
                <div class="stat-chip bg-{color_name}">{label}</div>
                <p class="stat-context">{context}</p>
            </div>
        </div>
        """
    elif visual_action == "concept_flow":
        steps = visual_data.get("steps", ["Input", "Process", "Output"])
        arrows = visual_data.get("arrows", ["→", "→"])
        steps_html = ""
        colors = ["indigo", "amber", "emerald", "purple"]
        for idx, step in enumerate(steps[:4]):
            steps_html += f"""
            <div class="step-card border-{colors[idx%4]}" style="animation-delay: {idx*0.3}s">
                <div class="step-num bg-{colors[idx%4]}">{idx+1}</div>
                <div class="step-text">{step.replace('"', '&quot;')}</div>
            </div>
            """
            if idx < len(steps[:4]) - 1:
                arr = arrows[idx] if idx < len(arrows) else "→"
                steps_html += f"""
                <div class="step-arrow" style="animation-delay: {idx*0.3 + 0.15}s">
                    <div class="arrow-symbol">→</div>
                    <div class="arrow-label">{arr.replace('"', '&quot;')}</div>
                </div>
                """
        card_html = f"""
        <div class="concept-flow-container">
            <h1 class="flow-title">{title}</h1>
            <div class="flow-row">
                {steps_html}
            </div>
        </div>
        """

    # 2. Split Screen Visuals HTML (top half visualizer, bottom half editor)
    split_html = ""
    if not card_html:
        visual_html = ""
        
        # Determine top half visualization HTML
        if visual_action in ("show_grid", "place_char", "highlight_row", "show_arrows"):
            rows = visual_data.get("rows", 4)
            cols = visual_data.get("cols", 4)
            grid = visual_data.get("grid", [["" for _ in range(cols)] for _ in range(rows)])
            
            cells_html = ""
            for r in range(rows):
                for c in range(cols):
                    val = grid[r][c] if r < len(grid) and c < len(grid[r]) else ""
                    
                    cell_class = ""
                    if visual_action == "place_char" and r == visual_data.get("row") and c == visual_data.get("col"):
                        cell_class = "cell-placed"
                    elif visual_action == "highlight_row" and r == visual_data.get("row"):
                        cell_class = "cell-highlighted-row"
                        
                    cells_html += f"""
                    <div class="grid-cell cell-{r}-{c} {cell_class}" style="grid-row: {r+1}; grid-column: {c+1};">
                        <span class="cell-idx">{r},{c}</span>
                        <span class="cell-content">{val}</span>
                    </div>
                    """
            
            row_overlay = ""
            if visual_action == "highlight_row":
                tr = visual_data.get("row", 0)
                row_overlay = f'<div class="grid-row-overlay" style="grid-row: {tr+1}; grid-column: 1 / span {cols};"></div>'
                
            visual_html = f"""
            <div class="grid-container" style="grid-template-rows: repeat({rows}, 1fr); grid-template-columns: repeat({cols}, 1fr);">
                {cells_html}
                {row_overlay}
                <svg id="arrow-svg" class="svg-overlay"></svg>
            </div>
            """
        
        elif visual_action in ("show_array", "highlight_element", "show_pointers", "show_mid", "show_found", "show_not_found"):
            values = visual_data.get("values", [10, 20, 30, 40, 50])
            cols = len(values)
            
            cells_html = ""
            for c in range(cols):
                val = values[c]
                
                cell_class = ""
                if visual_action == "highlight_element" and c == visual_data.get("highlight_idx", 0):
                    cell_class = "cell-placed"
                elif visual_action == "show_found" and c == visual_data.get("found_idx", 0):
                    cell_class = "cell-found"
                    
                cells_html += f"""
                <div class="grid-cell cell-0-{c} {cell_class}" style="grid-row: 1; grid-column: {c+1};">
                    <span class="cell-content">{val}</span>
                    <span class="cell-idx-bottom">{c}</span>
                </div>
                """
            
            visual_html = f"""
            <div class="array-container" style="grid-template-columns: repeat({cols}, 1fr);">
                {cells_html}
                <svg id="arrow-svg" class="svg-overlay"></svg>
            </div>
            """
            
        elif visual_action == "show_bars":
            values = visual_data.get("values", [6, 3, 8, 1, 9, 4])
            sorted_count = visual_data.get("sorted_count", 0)
            n = len(values)
            max_val = max(values) if values else 1
            
            bars_html = ""
            for i, val in enumerate(values):
                h_pct = (val / max_val) * 100
                is_sorted = (i >= n - sorted_count)
                bar_class = "bar-emerald" if is_sorted else "bar-indigo"
                
                bars_html += f"""
                <div class="sorting-bar-wrapper">
                    <div class="sorting-bar-label">{val}</div>
                    <div class="sorting-bar {bar_class}" style="height: {h_pct}%; animation-delay: {i*0.1}s"></div>
                </div>
                """
            visual_html = f"""
            <div class="bars-container">
                {bars_html}
            </div>
            """
            
        elif visual_action == "show_stack":
            values = visual_data.get("values", ["A", "B", "C"])
            label = visual_data.get("label", "Stack")
            
            elements_html = ""
            for i, val in enumerate(values[:5]):
                # animate drop down
                delay = i * 0.2
                elements_html += f"""
                <div class="stack-element" style="animation-delay: {delay}s">
                    {val}
                    {f'<span class="stack-top-pointer">← TOP</span>' if i == len(values)-1 else ''}
                </div>
                """
            visual_html = f"""
            <div class="stack-container-wrapper">
                <div class="stack-header-label">{label}</div>
                <div class="stack-cup">
                    {elements_html}
                </div>
            </div>
            """
            
        elif visual_action in ("show_tree", "show_graph"):
            nodes = visual_data.get("nodes", [0, 1, 2, 3, 4, 5]) if visual_action == "show_graph" else visual_data.get("values", [5, 3, 7, 1, 4, 6, 8])
            
            # Simple list templates to render nodes
            nodes_html = ""
            for idx, nd in enumerate(nodes[:7]):
                is_hi = (idx == visual_data.get("highlight_idx", -1) or str(nd) in visual_data.get("visited", []))
                node_class = "node-green" if is_hi else "node-indigo"
                nodes_html += f'<div class="tree-node node-pos-{idx} {node_class}">{nd}</div>'
                
            visual_html = f"""
            <div class="tree-container">
                <svg id="arrow-svg" class="svg-overlay"></svg>
                {nodes_html}
            </div>
            """
        elif visual_action == "show_dp_table":
            values = visual_data.get("values", [0, 1, 1, 2, 3, 5])
            cols = len(values)
            cur_idx = visual_data.get("current_idx", -1)
            
            cells_html = ""
            for c in range(cols):
                val = values[c]
                cell_class = "cell-placed" if c == cur_idx else ""
                cells_html += f"""
                <div class="grid-cell cell-0-{c} {cell_class}" style="grid-row: 1; grid-column: {c+1};">
                    <span class="cell-content">{val}</span>
                    <span class="cell-idx-bottom">{c}</span>
                </div>
                """
            visual_html = f"""
            <div class="array-container" style="grid-template-columns: repeat({cols}, 1fr);">
                {cells_html}
                <svg id="arrow-svg" class="svg-overlay"></svg>
            </div>
            """
        else: # show_code default upper half
            # Empty grid placeholder
            visual_html = """
            <div class="grid-container" style="grid-template-rows: repeat(4, 1fr); grid-template-columns: repeat(4, 1fr); opacity: 0.2">
                <div class="grid-cell" style="grid-row: 1; grid-column: 1"></div>
                <div class="grid-cell" style="grid-row: 2; grid-column: 2"></div>
                <div class="grid-cell" style="grid-row: 3; grid-column: 3"></div>
                <div class="grid-cell" style="grid-row: 4; grid-column: 4"></div>
            </div>
            """
            
        # Compile Bottom Half Code Editor HTML
        code_lines = visual_data.get("lines", DEFAULT_CODE_LINES)
        highlight_line = visual_data.get("highlight_line")
        if highlight_line is None and visual_action == "highlight_code_line":
            highlight_line = 0
            
        code_lines_html = ""
        for idx, line in enumerate(code_lines[:7]):
            hl_class = "code-line-active" if idx == highlight_line else ""
            highlighted_code = _highlight_code_line_html(line)
            
            code_lines_html += f"""
            <div class="code-line {hl_class}">
                <span class="code-line-num">{idx+1}</span>
                <div class="code-line-content">{highlighted_code}</div>
            </div>
            """
            
        split_html = f"""
        <div class="split-screen">
            <div class="visualizer-area">
                {visual_html}
            </div>
            <div class="divider-line"></div>
            <div class="code-editor-area">
                <div class="mac-window">
                    <div class="mac-header">
                        <div class="mac-buttons">
                            <span class="btn btn-red"></span>
                            <span class="btn btn-yellow"></span>
                            <span class="btn btn-green"></span>
                        </div>
                        <div class="mac-title">solution.py</div>
                    </div>
                    <div class="mac-content">
                        {code_lines_html}
                    </div>
                </div>
            </div>
        </div>
        """

    # 3. Dynamic Javascript Parameters Injector
    # Inject JSON params for visual layouts in SVG
    arrows_json = "[]"
    if visual_action == "show_arrows":
        arrows_json = json.dumps(visual_data.get("arrows", []))
        
    array_pointers_js = ""
    if visual_action in ("show_pointers", "show_mid", "highlight_element", "show_found"):
        lo = visual_data.get("lo", "null")
        hi = visual_data.get("hi", "null")
        mid = visual_data.get("mid_idx", "null")
        hi_idx = visual_data.get("highlight_idx", "null")
        found_idx = visual_data.get("found_idx", "null")
        
        array_pointers_js = f"""
        const lo = {lo};
        const hi = {hi};
        const mid = {mid};
        const highlight_idx = {hi_idx};
        const found_idx = {found_idx};
        const cols = {len(visual_data.get("values", [1,2,3]))};
        
        const svg = document.getElementById('arrow-svg');
        if (svg) {{
            const svgRect = svg.getBoundingClientRect();
            
            if (lo !== null && lo < cols) {{
                const cell = document.querySelector('.cell-0-' + lo);
                if (cell) {{
                    const cellRect = cell.getBoundingClientRect();
                    const cx = cellRect.left + cellRect.width/2 - svgRect.left;
                    const cy = cellRect.bottom + 10 - svgRect.top;
                    
                    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    path.setAttribute('class', 'pointer-path pointer-green');
                    path.setAttribute('d', `M ${{cx}} ${{cy+22}} L ${{cx}} ${{cy}}`);
                    svg.appendChild(path);
                    
                    const head = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
                    head.setAttribute('class', 'pointer-head head-green');
                    head.setAttribute('points', `${{cx}},${{cy}} ${{cx-5}},${{cy+7}} ${{cx+5}},${{cy+7}}`);
                    svg.appendChild(head);
                    
                    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    txt.setAttribute('class', 'pointer-text text-green');
                    txt.setAttribute('x', cx);
                    txt.setAttribute('y', cy + 34);
                    txt.textContent = 'lo';
                    svg.appendChild(txt);
                }}
            }}
            
            if (hi !== null && hi < cols) {{
                const cell = document.querySelector('.cell-0-' + hi);
                if (cell) {{
                    const cellRect = cell.getBoundingClientRect();
                    const cx = cellRect.left + cellRect.width/2 - svgRect.left;
                    const cy = cellRect.bottom + 10 - svgRect.top;
                    
                    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    path.setAttribute('class', 'pointer-path pointer-rose');
                    path.setAttribute('d', `M ${{cx}} ${{cy+22}} L ${{cx}} ${{cy}}`);
                    svg.appendChild(path);
                    
                    const head = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
                    head.setAttribute('class', 'pointer-head head-rose');
                    head.setAttribute('points', `${{cx}},${{cy}} ${{cx-5}},${{cy+7}} ${{cx+5}},${{cy+7}}`);
                    svg.appendChild(head);
                    
                    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    txt.setAttribute('class', 'pointer-text text-rose');
                    txt.setAttribute('x', cx);
                    txt.setAttribute('y', cy + 34);
                    txt.textContent = 'hi';
                    svg.appendChild(txt);
                }}
            }}
            
            if (mid !== null && mid < cols) {{
                const cell = document.querySelector('.cell-0-' + mid);
                if (cell) {{
                    const cellRect = cell.getBoundingClientRect();
                    const cx = cellRect.left + cellRect.width/2 - svgRect.left;
                    const cy = cellRect.top - 10 - svgRect.top;
                    
                    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    path.setAttribute('class', 'pointer-path pointer-amber');
                    path.setAttribute('d', `M ${{cx}} ${{cy-22}} L ${{cx}} ${{cy}}`);
                    svg.appendChild(path);
                    
                    const head = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
                    head.setAttribute('class', 'pointer-head head-amber');
                    head.setAttribute('points', `${{cx}},${{cy}} ${{cx-5}},${{cy-7}} ${{cx+5}},${{cy-7}}`);
                    svg.appendChild(head);
                    
                    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    txt.setAttribute('class', 'pointer-text text-amber');
                    txt.setAttribute('x', cx);
                    txt.setAttribute('y', cy - 28);
                    txt.textContent = 'mid';
                    svg.appendChild(txt);
                }}
            }}
            
            if (highlight_idx !== null && highlight_idx < cols) {{
                const cell = document.querySelector('.cell-0-' + highlight_idx);
                if (cell) {{
                    const cellRect = cell.getBoundingClientRect();
                    const cx = cellRect.left + cellRect.width/2 - svgRect.left;
                    const cy = cellRect.top - 10 - svgRect.top;
                    
                    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    path.setAttribute('class', 'pointer-path pointer-amber');
                    path.setAttribute('d', `M ${{cx}} ${{cy-22}} L ${{cx}} ${{cy}}`);
                    svg.appendChild(path);
                    
                    const head = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
                    head.setAttribute('class', 'pointer-head head-amber');
                    head.setAttribute('points', `${{cx}},${{cy}} ${{cx-5}},${{cy-7}} ${{cx+5}},${{cy-7}}`);
                    svg.appendChild(head);
                    
                    const label = "{visual_data.get("label", "Target")}";
                    if (label) {{
                        const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                        txt.setAttribute('class', 'pointer-text text-amber');
                        txt.setAttribute('x', cx);
                        txt.setAttribute('y', cy - 28);
                        txt.textContent = label;
                        svg.appendChild(txt);
                    }}
                }}
            }}
        }}
        """
        
    tree_lines_js = ""
    if visual_action in ("show_tree", "show_graph"):
        is_graph_val = "true" if visual_action == "show_graph" else "false"
        edges = [[0,1],[0,2],[1,3],[1,4],[2,5],[2,6]] if visual_action == "show_tree" else visual_data.get("edges", [[0,1],[1,2],[2,3],[3,0]])
        
        tree_lines_js = f"""
        const isGraph = {is_graph_val};
        const edges = {json.dumps(edges)};
        const svg = document.getElementById('arrow-svg');
        if (svg) {{
            const svgRect = svg.getBoundingClientRect();
            
            edges.forEach(edge => {{
                const uNode = document.querySelector('.node-pos-' + edge[0]);
                const vNode = document.querySelector('.node-pos-' + edge[1]);
                if (uNode && vNode) {{
                    const uRect = uNode.getBoundingClientRect();
                    const vRect = vNode.getBoundingClientRect();
                    
                    const x1 = uRect.left + uRect.width/2 - svgRect.left;
                    const y1 = uRect.top + uRect.height/2 - svgRect.top;
                    const x2 = vRect.left + vRect.width/2 - svgRect.left;
                    const y2 = vRect.top + vRect.height/2 - svgRect.top;
                    
                    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    line.setAttribute('class', 'tree-edge-line');
                    line.setAttribute('x1', x1);
                    line.setAttribute('y1', y1);
                    line.setAttribute('x2', x2);
                    line.setAttribute('y2', y2);
                    svg.appendChild(line);
                }}
            }});
        }}
        """

    # Complete HTML Page template
    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Warm-UI Animation Beat</title>
    <!-- Import Premium Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;900&family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --duration: 3s;
            --duration-ms: 3000ms;
            
            --bg-dark-start: #1C1917;
            --bg-dark-end: #0F0E0D;
            --white-stone: #FAF8F6;
            --stone-muted: #8C827A;
            
            --col-indigo: #6366F1;
            --col-emerald: #10B981;
            --col-rose: #F43F5E;
            --col-amber: #F59E0B;
            --col-purple: #C084FC;
            --col-blue: #38BDF8;
        }}
        
        * {{
            box-sizing: border-box;
        }}
        
        body {{
            margin: 0;
            padding: 0;
            width: 720px;
            height: 1280px;
            background: linear-gradient(135deg, var(--bg-dark-start) 0%, var(--bg-dark-end) 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            font-family: 'Outfit', 'Noto Sans', 'Noto Sans Devanagari', sans-serif;
            overflow: hidden;
            color: var(--white-stone);
        }}
        
        /* ── Full-Screen Card Layouts ──────────────────────────────────────── */
        
        .title-card-container {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 100%;
            padding: 60px;
        }}
        .chips {{
            display: flex;
            gap: 15px;
            margin-bottom: 50px;
        }}
        .chip {{
            width: 80px;
            height: 24px;
            border-radius: 12px;
            transform: scale(0);
            animation: zoomIn calc(var(--duration) * 0.15) cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
        }}
        .chip-indigo {{ background: var(--col-indigo); animation-delay: 0.1s; }}
        .chip-emerald {{ background: var(--col-emerald); animation-delay: 0.2s; }}
        .chip-rose {{ background: var(--col-rose); animation-delay: 0.3s; }}
        .chip-amber {{ background: var(--col-amber); animation-delay: 0.4s; }}
        .chip-purple {{ background: var(--col-purple); animation-delay: 0.5s; }}
        
        .title-text {{
            font-size: 48px;
            font-weight: 900;
            text-align: center;
            margin: 0 0 20px 0;
            opacity: 0;
            transform: translateY(30px);
            animation: fadeInUp calc(var(--duration) * 0.15) ease-out forwards;
            animation-delay: 0.2s;
        }}
        .title-bar {{
            width: 0;
            height: 4px;
            background: var(--col-indigo);
            border-radius: 2px;
            box-shadow: 0 0 10px rgba(99, 102, 241, 0.5);
            margin-bottom: 30px;
            animation: drawLine calc(var(--duration) * 0.15) ease-out forwards;
            animation-delay: 0.4s;
        }}
        .subtitle-text {{
            font-size: 24px;
            font-weight: 700;
            color: var(--col-amber);
            text-align: center;
            margin: 0;
            opacity: 0;
            transform: translateY(20px);
            animation: fadeInUp calc(var(--duration) * 0.15) ease-out forwards;
            animation-delay: 0.6s;
        }}
        
        /* CTA Card */
        .cta-card-container {{
            width: 100%;
            height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 50px;
        }}
        .cta-box {{
            width: 100%;
            border-radius: 28px;
            background: rgba(99, 102, 241, 0.08);
            border: 3px solid rgba(99, 102, 241, 0.7);
            padding: 50px 40px;
            display: flex;
            flex-direction: column;
            align-items: center;
            transform: scale(0.7);
            opacity: 0;
            animation: zoomIn calc(var(--duration) * 0.15) cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }}
        .bell-icon {{
            font-size: 64px;
            margin-bottom: 25px;
            animation: shake 1.2s ease-in-out infinite alternate;
            animation-delay: 0.3s;
        }}
        .cta-title {{
            font-size: 38px;
            font-weight: 800;
            text-align: center;
            margin: 0 0 15px 0;
            opacity: 0;
            transform: translateY(20px);
            animation: fadeInUp calc(var(--duration) * 0.15) ease-out forwards;
            animation-delay: 0.4s;
        }}
        .cta-channel {{
            font-size: 24px;
            color: var(--col-amber);
            margin: 0 0 35px 0;
            opacity: 0;
            transform: translateY(15px);
            animation: fadeInUp calc(var(--duration) * 0.15) ease-out forwards;
            animation-delay: 0.5s;
        }}
        .cta-footer {{
            font-size: 18px;
            font-weight: 700;
            color: var(--stone-muted);
            opacity: 0;
            animation: fadeIn calc(var(--duration) * 0.15) ease-out forwards;
            animation-delay: 0.7s;
        }}
        
        /* Text Only */
        .text-card-container {{
            width: 100%;
            height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 40px;
        }}
        .text-box {{
            padding: 30px 45px;
            border-radius: 20px;
            font-size: 34px;
            font-weight: 800;
            text-align: center;
            transform: scale(0.8);
            opacity: 0;
            animation: zoomIn calc(var(--duration) * 0.15) cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }}
        .text-accent {{ background: rgba(99, 102, 241, 0.1); border: 3px solid var(--col-indigo); }}
        .text-green {{ background: rgba(16, 185, 129, 0.1); border: 3px solid var(--col-emerald); }}
        .text-yellow {{ background: rgba(245, 158, 11, 0.1); border: 3px solid var(--col-amber); }}
        .text-red {{ background: rgba(244, 63, 94, 0.1); border: 3px solid var(--col-rose); }}
        
        /* Complexity Card */
        .complexity-container {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 100%;
        }}
        .comp-title {{
            font-size: 32px;
            font-weight: 800;
            margin: 0 0 35px 0;
            opacity: 0;
            transform: translateY(20px);
            animation: fadeInUp calc(var(--duration) * 0.15) ease-out forwards;
        }}
        .comp-card {{
            width: 600px;
            border-radius: 24px;
            background: rgba(38, 35, 34, 0.9);
            border: 3px solid rgba(99, 102, 241, 0.7);
            padding: 45px;
            display: flex;
            flex-direction: column;
            align-items: center;
            opacity: 0;
            transform: scale(0.9);
            animation: zoomIn calc(var(--duration) * 0.15) cubic-bezier(0.16, 1, 0.3, 1) forwards;
            animation-delay: 0.15s;
        }}
        .comp-label {{
            font-size: 18px;
            font-weight: 700;
            color: var(--stone-muted);
            margin-bottom: 10px;
        }}
        .comp-value {{
            font-size: 54px;
            font-weight: 900;
            margin-bottom: 30px;
            opacity: 0;
            transform: scale(0.8);
            animation: zoomIn calc(var(--duration) * 0.15) cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
        }}
        .val-time {{ color: var(--col-amber); animation-delay: 0.4s; }}
        .val-space {{ color: var(--col-emerald); animation-delay: 0.8s; margin-bottom: 0; }}
        .comp-divider {{
            width: 100%;
            height: 1.5px;
            background: rgba(140, 130, 122, 0.2);
            margin-bottom: 30px;
            opacity: 0;
            animation: fadeIn calc(var(--duration) * 0.1) forwards;
            animation-delay: 0.6s;
        }}
        
        /* Comparison */
        .comparison-container {{
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}
        .comp-row {{
            display: flex;
            align-items: center;
            gap: 25px;
            margin-top: 30px;
        }}
        .comp-box {{
            width: 270px;
            height: 320px;
            border-radius: 20px;
            padding: 40px 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: space-between;
            position: relative;
            opacity: 0;
            transform: scale(0.9);
            animation: zoomIn calc(var(--duration) * 0.15) cubic-bezier(0.16, 1, 0.3, 1) forwards;
            animation-delay: 0.15s;
        }}
        .box-winner {{
            background: rgba(16, 185, 129, 0.05);
            border: 3px solid var(--col-emerald);
        }}
        .box-loser {{
            background: rgba(244, 63, 94, 0.05);
            border: 3px solid var(--col-rose);
        }}
        .box-label {{
            font-size: 20px;
            font-weight: 700;
            color: var(--stone-muted);
        }}
        .box-value {{
            font-size: 44px;
            font-weight: 900;
        }}
        .vs-label {{
            font-size: 32px;
            font-weight: 900;
            color: var(--col-amber);
            opacity: 0;
            animation: fadeIn calc(var(--duration) * 0.15) forwards;
            animation-delay: 0.4s;
        }}
        .winner-tag {{
            background: var(--col-emerald);
            color: var(--bg-dark-end);
            font-size: 13px;
            font-weight: 900;
            padding: 6px 14px;
            border-radius: 8px;
            position: absolute;
            top: -20px;
            opacity: 0;
            transform: scale(0.5);
            animation: zoomIn calc(var(--duration) * 0.15) cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
            animation-delay: 0.8s;
        }}
        
        /* Icon Card */
        .icon-card-container {{
            width: 100%;
            height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 50px;
        }}
        .icon-box {{
            width: 100%;
            border-radius: 24px;
            padding: 40px;
            display: flex;
            align-items: center;
            gap: 30px;
            background: rgba(38, 35, 34, 0.8);
            opacity: 0;
            transform: scale(0.9);
            animation: zoomIn calc(var(--duration) * 0.15) cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }}
        .border-accent {{ border: 3px solid var(--col-indigo); }}
        .border-green {{ border: 3px solid var(--col-emerald); }}
        .border-yellow {{ border: 3px solid var(--col-amber); }}
        .border-red {{ border: 3px solid var(--col-rose); }}
        
        .icon-graphic {{
            width: 100px;
            height: 100px;
            display: flex;
            justify-content: center;
            align-items: center;
            opacity: 0;
            transform: scale(0.5);
            animation: zoomIn calc(var(--duration) * 0.18) cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
            animation-delay: 0.3s;
        }}
        .icon-text-block {{
            flex: 1;
        }}
        .icon-title {{
            font-size: 28px;
            font-weight: 800;
            margin: 0 0 10px 0;
            opacity: 0;
            transform: translateX(-20px);
            animation: slideIn calc(var(--duration) * 0.15) forwards;
            animation-delay: 0.4s;
        }}
        .icon-body {{
            font-size: 18px;
            color: var(--stone-muted);
            margin: 0;
            opacity: 0;
            transform: translateX(-20px);
            animation: slideIn calc(var(--duration) * 0.15) forwards;
            animation-delay: 0.5s;
        }}
        
        /* Bullet List */
        .bullet-list-container {{
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: 60px;
        }}
        .bullet-title {{
            font-size: 32px;
            font-weight: 800;
            text-align: center;
            margin: 0 0 40px 0;
            opacity: 0;
            animation: fadeIn calc(var(--duration) * 0.15) forwards;
        }}
        .bullet-items {{
            display: flex;
            flex-direction: column;
            gap: 20px;
            position: relative;
        }}
        .bullet-row {{
            display: flex;
            align-items: center;
            gap: 20px;
            opacity: 0;
            transform: translateX(-30px);
            animation: slideIn calc(var(--duration) * 0.18) forwards;
        }}
        .bullet-num {{
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 16px;
            font-weight: 800;
            color: var(--bg-dark-end);
        }}
        .bullet-text {{
            font-size: 20px;
            font-weight: 700;
        }}
        .bg-accent {{ background: var(--col-indigo); }}
        .bg-green {{ background: var(--col-emerald); }}
        .bg-yellow {{ background: var(--col-amber); }}
        .bg-red {{ background: var(--col-rose); }}
        
        /* Stat Callout */
        .stat-card-container {{
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 40px;
            padding: 50px;
        }}
        .stat-graphic {{
            width: 220px;
            height: 220px;
            position: relative;
            opacity: 0;
            transform: scale(0.6);
            animation: zoomIn calc(var(--duration) * 0.18) cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
        }}
        .stat-rings {{
            width: 100%;
            height: 100%;
            border-radius: 50%;
            border: 4px solid var(--col-amber);
            background: rgba(245, 158, 11, 0.08);
            display: flex;
            justify-content: center;
            align-items: center;
            box-shadow: inset 0 0 20px rgba(245, 158, 11, 0.2);
        }}
        .stat-rings.border-accent {{ border-color: var(--col-indigo); background: rgba(99, 102, 241, 0.08); box-shadow: inset 0 0 20px rgba(99, 102, 241, 0.2); }}
        .stat-rings.border-green {{ border-color: var(--col-emerald); background: rgba(16, 185, 129, 0.08); box-shadow: inset 0 0 20px rgba(16, 185, 129, 0.2); }}
        .stat-rings.border-red {{ border-color: var(--col-rose); background: rgba(244, 63, 94, 0.08); box-shadow: inset 0 0 20px rgba(244, 63, 94, 0.2); }}
        
        .stat-value {{
            font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace;
            font-size: 32px;
            font-weight: 800;
            text-align: center;
        }}
        .stat-text-block {{
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: flex-start;
        }}
        .stat-chip {{
            padding: 8px 18px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 800;
            color: var(--bg-dark-end);
            margin-bottom: 20px;
            opacity: 0;
            transform: translateY(15px);
            animation: fadeInUp calc(var(--duration) * 0.15) forwards;
            animation-delay: 0.4s;
        }}
        .stat-context {{
            font-size: 18px;
            color: var(--stone-muted);
            margin: 0;
            opacity: 0;
            transform: translateY(15px);
            animation: fadeInUp calc(var(--duration) * 0.15) forwards;
            animation-delay: 0.5s;
        }}
        
        /* Concept Flow */
        .concept-flow-container {{
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 30px;
        }}
        .flow-title {{
            font-size: 32px;
            font-weight: 800;
            margin: 0 0 50px 0;
            opacity: 0;
            animation: fadeIn calc(var(--duration) * 0.15) forwards;
        }}
        .flow-row {{
            display: flex;
            align-items: center;
            width: 100%;
            justify-content: center;
        }}
        .step-card {{
            width: 135px;
            height: 120px;
            border-radius: 20px;
            background: rgba(38, 35, 34, 0.8);
            border-width: 2.5px;
            border-style: solid;
            padding: 20px 10px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: space-between;
            position: relative;
            opacity: 0;
            transform: scale(0.7);
            animation: zoomIn calc(var(--duration) * 0.15) cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
        }}
        .step-num {{
            width: 20px;
            height: 20px;
            border-radius: 50%;
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 10px;
            font-weight: 800;
            color: var(--bg-dark-end);
            position: absolute;
            top: 10px;
            left: 10px;
        }}
        .step-text {{
            font-size: 16px;
            font-weight: 700;
            margin-top: 15px;
            text-align: center;
        }}
        .step-arrow {{
            display: flex;
            flex-direction: column;
            align-items: center;
            margin: 0 5px;
            opacity: 0;
            animation: fadeIn calc(var(--duration) * 0.15) forwards;
        }}
        .arrow-symbol {{
            font-size: 24px;
            color: var(--stone-muted);
            animation: slideRight 1.5s infinite alternate;
        }}
        .arrow-label {{
            font-size: 12px;
            color: var(--col-amber);
            font-weight: 700;
        }}
        
        .border-indigo {{ border-color: var(--col-indigo); }}
        .border-amber {{ border-color: var(--col-amber); }}
        .border-emerald {{ border-color: var(--col-emerald); }}
        .border-purple {{ border-color: var(--col-purple); }}
        
        /* ── Split-Screen Visualizations ──────────────────────────────────── */
        
        .split-screen {{
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            padding: 40px 30px;
        }}
        
        .visualizer-area {{
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            position: relative;
        }}
        
        .divider-line {{
            width: 100%;
            height: 1px;
            background: rgba(63, 57, 53, 0.4);
            margin: 25px 0;
        }}
        
        .code-editor-area {{
            height: 380px;
            display: flex;
            justify-content: center;
        }}
        
        /* 1D Array Layout */
        .array-container {{
            display: grid;
            gap: 10px;
            width: 100%;
            max-width: 640px;
            position: relative;
            margin-top: -20px;
        }}
        
        /* 2D Grid Layout */
        .grid-container {{
            display: grid;
            gap: 8px;
            width: 100%;
            max-width: 600px;
            height: 360px;
            position: relative;
        }}
        
        .grid-cell {{
            background: var(--white-stone);
            background-color: rgba(38, 35, 34, 0.9);
            border: 1.5px solid var(--COLOR_TILE_BORDER, rgba(63, 57, 53, 0.6));
            border-radius: 12px;
            display: flex;
            justify-content: center;
            align-items: center;
            position: relative;
            font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace;
            font-weight: 700;
        }}
        
        .cell-idx {{
            font-family: 'Outfit', 'Noto Sans', 'Noto Sans Devanagari', sans-serif;
            font-size: 9px;
            color: var(--stone-muted);
            position: absolute;
            top: 5px;
            left: 6px;
            opacity: 0.4;
        }}
        .cell-idx-bottom {{
            font-family: 'Outfit', 'Noto Sans', 'Noto Sans Devanagari', sans-serif;
            font-size: 14px;
            font-weight: 700;
            color: var(--stone-muted);
            position: absolute;
            bottom: -24px;
            left: 50%;
            transform: translateX(-50%);
        }}
        
        .cell-content {{
            font-size: 24px;
            color: var(--white-stone);
        }}
        
        .cell-placed {{
            background: #3B2E21;
            border-color: var(--col-amber);
            border-width: 3px;
            box-shadow: 0 0 15px rgba(245, 158, 11, 0.25);
            animation: zoomCell calc(var(--duration) * 0.15) cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
        }}
        
        .cell-found {{
            background: #143525;
            border-color: var(--col-emerald);
            border-width: 3px;
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.25);
            animation: zoomCell calc(var(--duration) * 0.15) cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
        }}
        
        .cell-highlighted-row {{
            background: rgba(40, 50, 70, 0.4);
            border-color: var(--col-blue);
        }}
        
        .grid-row-overlay {{
            border: 3.5px solid var(--col-blue);
            border-radius: 14px;
            pointer-events: none;
            box-shadow: 0 0 20px rgba(56, 189, 248, 0.15);
            animation: fadeOutline calc(var(--duration) * 0.15) ease-out forwards;
        }}
        
        /* Sorting Bars */
        .bars-container {{
            display: flex;
            align-items: flex-end;
            justify-content: center;
            gap: 12px;
            width: 100%;
            height: 240px;
        }}
        .sorting-bar-wrapper {{
            display: flex;
            flex-direction: column;
            align-items: center;
            flex: 1;
            max-width: 50px;
        }}
        .sorting-bar {{
            width: 100%;
            border-radius: 6px;
            border-width: 1.5px;
            border-style: solid;
            transform: scaleY(0);
            transform-origin: bottom;
            animation: growBar calc(var(--duration) * 0.2) cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }}
        .bar-indigo {{ background: rgba(99, 102, 241, 0.8); border-color: var(--col-indigo); }}
        .bar-emerald {{ background: rgba(16, 185, 129, 0.8); border-color: var(--col-emerald); }}
        .sorting-bar-label {{
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        
        /* Stack */
        .stack-container-wrapper {{
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        .stack-header-label {{
            font-size: 20px;
            font-weight: 800;
            color: var(--stone-muted);
            margin-bottom: 15px;
        }}
        .stack-cup {{
            width: 160px;
            height: 260px;
            border-left: 4px solid var(--stone-muted);
            border-right: 4px solid var(--stone-muted);
            border-bottom: 4px solid var(--stone-muted);
            display: flex;
            flex-direction: column-reverse;
            padding: 6px;
            gap: 6px;
        }}
        .stack-element {{
            width: 100%;
            height: 42px;
            background: rgba(99, 102, 241, 0.6);
            border: 2px solid var(--col-indigo);
            border-radius: 8px;
            display: flex;
            justify-content: center;
            align-items: center;
            font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace;
            font-size: 18px;
            font-weight: 700;
            position: relative;
            transform: translateY(-200px);
            opacity: 0;
            animation: dropElement calc(var(--duration) * 0.18) cubic-bezier(0.25, 1, 0.5, 1) forwards;
        }}
        .stack-top-pointer {{
            font-family: 'Outfit', 'Noto Sans', 'Noto Sans Devanagari', sans-serif;
            font-size: 13px;
            font-weight: 800;
            color: var(--col-emerald);
            position: absolute;
            left: 160px;
            white-space: nowrap;
        }}
        
        /* Tree Layout */
        .tree-container {{
            width: 600px;
            height: 380px;
            position: relative;
        }}
        .tree-node {{
            width: 44px;
            height: 44px;
            border-radius: 50%;
            border-width: 2.5px;
            border-style: solid;
            display: flex;
            justify-content: center;
            align-items: center;
            font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace;
            font-size: 15px;
            font-weight: 700;
            position: absolute;
            transform: translate(-50%, -50%) scale(0);
            animation: zoomIn calc(var(--duration) * 0.18) cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
            animation-delay: 0.2s;
            background: var(--bg-dark-end);
        }}
        .node-indigo {{ border-color: var(--col-indigo); box-shadow: 0 0 10px rgba(99, 102, 241, 0.15); }}
        .node-green {{ border-color: var(--col-emerald); box-shadow: 0 0 15px rgba(16, 185, 129, 0.3); background: #143525; }}
        
        /* Predefined binary tree positions */
        .node-pos-0 {{ left: 300px; top: 50px; }}
        .node-pos-1 {{ left: 180px; top: 140px; }}
        .node-pos-2 {{ left: 420px; top: 140px; }}
        .node-pos-3 {{ left: 100px; top: 250px; }}
        .node-pos-4 {{ left: 260px; top: 250px; }}
        .node-pos-5 {{ left: 340px; top: 250px; }}
        .node-pos-6 {{ left: 500px; top: 250px; }}
        
        /* SVG Overlay Pointers and Connector Lines */
        .svg-overlay {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            overflow: visible;
            z-index: 1;
        }}
        
        .arrow-path {{
            stroke: var(--col-rose);
            stroke-width: 4px;
            fill: none;
            stroke-linecap: round;
            stroke-dasharray: 1000;
            stroke-dashoffset: 1000;
            animation: drawArrow calc(var(--duration) * 0.2) ease-in-out forwards;
        }}
        
        .arrow-head {{
            fill: var(--col-rose);
            opacity: 0;
            animation: fadeIn calc(var(--duration) * 0.05) forwards;
            animation-delay: calc(var(--duration) * 0.16);
        }}
        
        .pointer-path {{
            stroke-width: 3px;
            fill: none;
            stroke-linecap: round;
            stroke-dasharray: 100;
            stroke-dashoffset: 100;
            animation: drawArrow calc(var(--duration) * 0.15) ease-out forwards;
        }}
        .pointer-head {{
            opacity: 0;
            animation: fadeIn calc(var(--duration) * 0.05) forwards;
            animation-delay: calc(var(--duration) * 0.12);
        }}
        .pointer-text {{
            font-size: 14px;
            font-weight: 800;
            text-anchor: middle;
            opacity: 0;
            animation: fadeIn calc(var(--duration) * 0.1) forwards;
            animation-delay: calc(var(--duration) * 0.14);
        }}
        
        .pointer-green {{ stroke: var(--col-emerald); }}
        .head-green {{ fill: var(--col-emerald); }}
        .text-green {{ fill: var(--col-emerald); }}
        
        .pointer-rose {{ stroke: var(--col-rose); }}
        .head-rose {{ fill: var(--col-rose); }}
        .text-rose {{ fill: var(--col-rose); }}
        
        .pointer-amber {{ stroke: var(--col-amber); }}
        .head-amber {{ fill: var(--col-amber); }}
        .text-amber {{ fill: var(--col-amber); }}
        
        .tree-edge-line {{
            stroke: var(--stone-muted);
            stroke-width: 2.5px;
            opacity: 0.3;
            stroke-dasharray: 500;
            stroke-dashoffset: 500;
            animation: drawArrow calc(var(--duration) * 0.15) ease-out forwards;
        }}
        
        /* ── Code Editor Styling ─────────────────────────────────────────── */
        
        .mac-window {{
            width: 650px;
            height: 360px;
            border-radius: 18px;
            background: rgba(24, 20, 18, 0.95);
            border: 1.5px solid rgba(63, 56, 50, 0.4);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
        }}
        
        .mac-header {{
            height: 48px;
            background: rgba(18, 15, 13, 0.95);
            display: flex;
            align-items: center;
            padding: 0 20px;
            position: relative;
            border-bottom: 1px solid rgba(63, 56, 50, 0.2);
        }}
        
        .mac-buttons {{
            display: flex;
            gap: 8px;
        }}
        
        .btn {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
        }}
        .btn-red {{ background: #FF5F56; }}
        .btn-yellow {{ background: #FFBD2E; }}
        .btn-green {{ background: #27C93F; }}
        
        .mac-title {{
            font-size: 14px;
            font-weight: 700;
            color: var(--stone-muted);
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
        }}
        
        .mac-content {{
            flex: 1;
            padding: 25px;
            display: flex;
            flex-direction: column;
            gap: 2px;
            font-family: 'JetBrains Mono', 'Noto Sans Mono', monospace;
            font-size: 16px;
            line-height: 1.6;
        }}
        
        .code-line {{
            display: flex;
            align-items: center;
            border-radius: 6px;
            height: 32px;
            padding: 0 10px;
            position: relative;
            width: 100%;
        }}
        
        .code-line-num {{
            width: 30px;
            color: rgba(140, 130, 122, 0.5);
            font-size: 14px;
            user-select: none;
        }}
        
        .code-line-content {{
            flex: 1;
            color: var(--white-stone);
            white-space: pre;
        }}
        
        /* Syntax Colors */
        .code-kw {{ color: var(--col-purple); font-weight: 700; }}
        .code-str {{ color: var(--col-emerald); }}
        .code-num {{ color: var(--col-amber); }}
        .code-op {{ color: var(--col-blue); }}
        .code-comment {{ color: var(--stone-muted); font-style: italic; }}
        
        /* Highlight Code Line */
        .code-line-active {{
            background: rgba(245, 158, 11, 0.12);
            box-shadow: inset 4px 0 0 var(--col-amber);
            animation: highlightIn calc(var(--duration) * 0.15) cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }}
        
        /* ── Animations ───────────────────────────────────────────────────── */
        
        @keyframes fadeIn {{
            to {{ opacity: 1; }}
        }}
        @keyframes fadeInUp {{
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        @keyframes slideIn {{
            to {{
                opacity: 1;
                transform: translateX(0);
            }}
        }}
        @keyframes zoomIn {{
            to {{
                opacity: 1;
                transform: scale(1);
            }}
        }}
        @keyframes drawLine {{
            to {{ width: 220px; }}
        }}
        @keyframes drawArrow {{
            to {{ stroke-dashoffset: 0; }}
        }}
        @keyframes shake {{
            0% {{ transform: rotate(-8deg); }}
            100% {{ transform: rotate(8deg); }}
        }}
        @keyframes highlightIn {{
            from {{
                background: rgba(245, 158, 11, 0);
                box-shadow: inset 0 0 0 var(--col-amber);
            }}
            to {{
                background: rgba(245, 158, 11, 0.12);
                box-shadow: inset 4px 0 0 var(--col-amber);
            }}
        }}
        @keyframes zoomCell {{
            0% {{ transform: scale(0.6); }}
            60% {{ transform: scale(1.08); }}
            100% {{ transform: scale(1); }}
        }}
        @keyframes growBar {{
            to {{ transform: scaleY(1); }}
        }}
        @keyframes dropElement {{
            0% {{ transform: translateY(-200px); opacity: 0; }}
            80% {{ transform: translateY(5px); opacity: 1; }}
            100% {{ transform: translateY(0); opacity: 1; }}
        }}
        @keyframes slideRight {{
            from {{ transform: translateX(-3px); }}
            to {{ transform: translateX(3px); }}
        }}
        .anim-pulse-delay {{
            animation: pulseWave 2s infinite alternate;
            animation-delay: 0.8s;
        }}
        @keyframes pulseWave {{
            to {{
                transform: scale(1.04);
                filter: drop-shadow(0 0 10px rgba(245, 158, 11, 0.3));
            }}
        }}
    </style>
</head>
<body>
    {card_html or split_html}
    
    <script>
        // Set animation duration variables dynamically from query params
        const urlParams = new URLSearchParams(window.location.search);
        const duration = parseFloat(urlParams.get('duration')) || 3.0;
        document.documentElement.style.setProperty('--duration', `${{duration}}s`);
        document.documentElement.style.setProperty('--duration-ms', `${{duration * 1000}}ms`);
        
        // 1. Dynamic SVG Arrow Connector logic
        {f"const arrows = {arrows_json};" if visual_action == "show_arrows" else "const arrows = [];"}
        if (arrows.length > 0) {{
            window.addEventListener('load', () => {{
                const svg = document.getElementById('arrow-svg');
                if (!svg) return;
                
                // wait brief moment for layout layout-flow
                setTimeout(() => {{
                    const svgRect = svg.getBoundingClientRect();
                    
                    arrows.forEach(arr => {{
                        const startCell = document.querySelector(`.cell-${{arr.start[0]}}-${{arr.start[1]}}`);
                        const endCell = document.querySelector(`.cell-${{arr.end[0]}}-${{arr.end[1]}}`);
                        if (!startCell || !endCell) return;
                        
                        const startRect = startCell.getBoundingClientRect();
                        const endRect = endCell.getBoundingClientRect();
                        
                        const x1 = startRect.left + startRect.width/2 - svgRect.left;
                        const y1 = startRect.top + startRect.height/2 - svgRect.top;
                        const x2 = endRect.left + endRect.width/2 - svgRect.left;
                        const y2 = endRect.top + endRect.height/2 - svgRect.top;
                        
                        // Draw Path
                        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                        path.setAttribute('class', 'arrow-path');
                        path.setAttribute('d', `M ${{x1}} ${{y1}} L ${{x2}} ${{y2}}`);
                        svg.appendChild(path);
                        
                        // Calculate angle & arrowhead
                        const angle = Math.atan2(y2 - y1, x2 - x1);
                        const arrowHead = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
                        arrowHead.setAttribute('class', 'arrow-head');
                        
                        const arrowSize = 13;
                        const tx = x2;
                        const ty = y2;
                        const pt1_x = tx - arrowSize * Math.cos(angle - Math.PI/6);
                        const pt1_y = ty - arrowSize * Math.sin(angle - Math.PI/6);
                        const pt2_x = tx - arrowSize * Math.cos(angle + Math.PI/6);
                        const pt2_y = ty - arrowSize * Math.sin(angle + Math.PI/6);
                        
                        arrowHead.setAttribute('points', `${{tx}},${{ty}} ${{pt1_x}},${{pt1_y}} ${{pt2_x}},${{pt2_y}}`);
                        svg.appendChild(arrowHead);
                    }});
                }}, 50);
            }});
        }}
        
        // 2. Dynamic Array Pointers logic
        {array_pointers_js}
        
        // 3. Dynamic Tree Connectors logic
        {tree_lines_js}
    </script>
</body>
</html>
"""
    return full_html


# ── Public API ────────────────────────────────────────────────────────────────

def render_beat(visual_action: str, visual_data: dict,
                duration: float, output_path: str) -> str | None:
    """
    Renders a single beat animation using headless Playwright Chrome.
    Returns output_path on success, None on failure.
    """
    logger.info(f"[Chrome Beat] Compiling HTML & rendering '{visual_action}' for {duration:.2f}s...")
    
    # Clean output path first
    if os.path.exists(output_path):
        try: os.remove(output_path)
        except: pass
        
    supported_actions = {
        "title_card", "show_grid", "place_char", "highlight_row", "show_arrows", "highlight_code_line",
        "show_array", "highlight_element", "show_pointers", "show_mid", "show_found", "show_not_found",
        "show_code", "show_complexity", "show_comparison", "show_tree", "show_stack", "show_bars",
        "show_dp_table", "show_graph", "text_only", "cta_card", "icon_card", "bullet_list", "stat_callout", "concept_flow"
    }
    
    if visual_action not in supported_actions:
        logger.warning(f"[Chrome Beat] Unknown action '{visual_action}', using text_only")
        visual_action = "text_only"
        visual_data = {"text": visual_action.replace("_", " ").title(), "color": "accent"}

    # Generate HTML content
    html_content = _generate_beat_html(visual_action, visual_data)
    
    # Write to a temp HTML file
    temp_dir = os.path.join(RENDER_DIR, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_html_path = os.path.join(temp_dir, f"_beat_{os.getpid()}_{visual_action}.html")
    
    try:
        with open(temp_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        # Playwright synchronous recording
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 720, "height": 1280},
                record_video_dir=temp_dir,
                record_video_size={"width": 720, "height": 1280}
            )
            page = context.new_page()
            
            # Load with exact duration query parameter so CSS animation rate matches audio
            file_url = f"file://{temp_html_path}?duration={duration}"
            page.goto(file_url)
            
            # Wait for the exact duration of the clip
            page.wait_for_timeout(int(duration * 1000))
            
            # Close context to write WebM video file
            recorded_webm = page.video.path()
            context.close()
            browser.close()
            
        if not recorded_webm or not os.path.exists(recorded_webm):
            logger.error("[Chrome Beat] WebM recording not found after closing browser")
            return None
            
        # Convert WebM to MP4 using FFmpeg
        logger.info(f"[Chrome Beat] Encoding WebM → MP4 via FFmpeg...")
        cmd = [
            "ffmpeg", "-y", "-i", recorded_webm,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            output_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        
        # Clean up intermediate WebM recording
        try: os.remove(recorded_webm)
        except: pass
        
        if res.returncode == 0 and os.path.exists(output_path):
            logger.info(f"[Chrome Beat] ✅ Rendered successfully: {output_path} ({duration:.2f}s)")
            return output_path
        else:
            logger.error(f"[Chrome Beat] FFmpeg conversion failed:\n{res.stderr}")
            return None
            
    except Exception as e:
        logger.error(f"[Chrome Beat] Render error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None
    finally:
        # Clean up temp HTML file
        try:
            if os.path.exists(temp_html_path):
                os.remove(temp_html_path)
        except:
            pass

# ── Subtitle Utilities ────────────────────────────────────────────────────────

def generate_srt(beats_with_timing: list) -> str:
    """
    Generates an SRT subtitle file from beats with timing.
    beats_with_timing: [{text, start_sec, end_sec}, ...]
    """
    entries = []
    for i, b in enumerate(beats_with_timing, 1):
        start = _sec_to_srt(b["start_sec"])
        end   = _sec_to_srt(b["end_sec"])
        text  = _wrap_subtitle(b["text"])
        entries.append(f"{i}\n{start} --> {end}\n{text}")
    return "\n\n".join(entries) + "\n"


def _sec_to_srt(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _wrap_subtitle(text: str, max_len: int = 48) -> str:
    """Wraps text into max 2 subtitle lines."""
    if len(text) <= max_len:
        return text
    words = text.split()
    line1, line2 = [], []
    for w in words:
        if len(" ".join(line1 + [w])) <= max_len:
            line1.append(w)
        else:
            line2.append(w)
    return " ".join(line1) + "\n" + " ".join(line2)


def burn_subtitles(video_path: str, srt_path: str, output_path: str) -> str | None:
    """Burns styled subtitles into video using MoviePy to bypass stripped ffmpeg builds."""
    try:
        from moviepy import VideoFileClip, TextClip, CompositeVideoClip
        
        video = VideoFileClip(video_path)
        
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        blocks = re.split(r'\n\s*\n', content.strip())
        subs = []
        
        def srt_time_to_seconds(t_str):
            h, m, s, ms = re.match(r'(\d+):(\d+):(\d+),(\d+)', t_str.strip()).groups()
            return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0
            
        for block in blocks:
            lines = block.split('\n')
            if len(lines) >= 3:
                times = lines[1].split(' --> ')
                if len(times) == 2:
                    start_t = srt_time_to_seconds(times[0])
                    end_t   = srt_time_to_seconds(times[1])
                    text    = "\n".join(lines[2:])
                    
                    if text.strip() and end_t > start_t:
                        # Create white text with a black stroke for high visibility
                        txt_clip = TextClip(
                            font="Arial.ttf", 
                            text=text, 
                            font_size=55, 
                            color='white',
                            stroke_color='black',
                            stroke_width=2,
                            text_align='center'
                        )
                        # Position nicely in the lower center
                        txt_clip = txt_clip.with_position(('center', video.h - 150))
                        txt_clip = txt_clip.with_start(start_t).with_duration(end_t - start_t)
                        subs.append(txt_clip)
                        
        final_video = CompositeVideoClip([video] + subs)
        final_video.write_videofile(
            output_path, 
            fps=video.fps, 
            codec="libx264", 
            audio_codec="aac",
            preset="ultrafast",
            logger=None
        )
        
        # Free resources
        video.close()
        final_video.close()
        
        logger.info(f"[Subtitles] ✅ Burned into: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"[Subtitles] MoviePy engine failed: {e}")
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Playwright beat renderer...")
    out = render_beat(
        "place_char",
        {"rows": 4, "cols": 4, "grid": [["A","B","C","D"], ["","","",""], ["","","",""], ["","","",""]], "row": 1, "col": 1, "char": "X"},
        duration=3.0,
        output_path="/Users/macbook/.gemini/antigravity/brain/2544c0fe-3be4-4c45-87d0-1385d749b1f9/scratch/test_chrome_place_char.mp4"
    )
    print(f"Result: {out}")
