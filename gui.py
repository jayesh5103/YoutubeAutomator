import os
import sys

# Auto-restart in virtual environment if not already running in one.
expected_venv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
if sys.prefix != expected_venv and os.path.exists(os.path.join(expected_venv, "bin", "python3")):
    print(f"🔄 Restarting gui.py within the project virtual environment ({expected_venv})...")
    os.execv(os.path.join(expected_venv, "bin", "python3"), [os.path.join(expected_venv, "bin", "python3")] + sys.argv)

import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
import threading
import queue
import webbrowser
import json
import csv
from datetime import datetime

# Import workflow logic modules
from main import job, run_scheduler, DAILY_VIDEO_LIMIT
import quota_manager
import database
import sqlite3
from youtube_uploader import get_channel_stats, upload_video
from pipeline_state import PipelineStatus, transition
import script_review_manager
import beat_renderer
import video_editor

# Optional VLC player import
try:
    import vlc
    VLC_AVAILABLE = True
except Exception:
    VLC_AVAILABLE = False

# --- Custom Theme/Colors ---
ACCENT_COLOR = "#6366f1"  # Indigo
SUCCESS_COLOR = "#10b981" # Emerald
WARNING_COLOR = "#f59e0b" # Amber
ERROR_COLOR = "#ef4444"   # Rose
BG_DARK = "#0f172a"       # Slate 900
CARD_BG = "#1e293b"       # Slate 800
SIDEBAR_BG = "#111827"    # Gray 900

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ConsoleDirector:
    """Redirects stdout to a tkinter text widget."""
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.queue = queue.Queue()
        self.update_widget()

    def write(self, string):
        self.queue.put(string)

    def flush(self):
        pass

    def update_widget(self):
        while not self.queue.empty():
            msg = self.queue.get()
            try:
                self.text_widget.configure(state="normal")
                self.text_widget.insert("end", msg)
                self.text_widget.see("end")
                self.text_widget.configure(state="disabled")
            except Exception:
                pass
        self.text_widget.after(100, self.update_widget)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI Coding Studio — Human Review & Approval Control Center")
        self.geometry("1280x850")
        self.configure(fg_color=BG_DARK)

        # Grid configuration
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.selected_script_pipeline_id = None
        self.selected_review_pipeline_id = None
        self.live_log_tail = True

        # --- Sidebar ---
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=SIDEBAR_BG, border_width=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(10, weight=1)
        
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="CODE STUDIO", 
                                      font=ctk.CTkFont(size=22, weight="bold", family="Inter"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 40))

        # Modern Nav Buttons
        self.sidebar_button_run = ctk.CTkButton(self.sidebar_frame, text="Generate Now 🪄", 
                                               height=40, font=ctk.CTkFont(weight="bold"),
                                               fg_color=ACCENT_COLOR, hover_color="#4f46e5",
                                               command=self.run_now_event)
        self.sidebar_button_run.grid(row=1, column=0, padx=20, pady=10)

        self.sidebar_button_sync = ctk.CTkButton(self.sidebar_frame, text="Sync Metrics 🔄", 
                                                height=40, font=ctk.CTkFont(weight="bold"),
                                                fg_color=CARD_BG, border_width=1, border_color=ACCENT_COLOR,
                                                hover_color="#334155",
                                                command=self.sync_stats_event)
        self.sidebar_button_sync.grid(row=2, column=0, padx=20, pady=10)

        self.sidebar_button_quota = ctk.CTkButton(self.sidebar_frame, text="Groq Quota 📊", 
                                                 height=32, font=ctk.CTkFont(size=12),
                                                 fg_color="transparent", border_width=1, border_color="#334155",
                                                 command=self.check_quota_event)
        self.sidebar_button_quota.grid(row=3, column=0, padx=20, pady=10)

        self.sidebar_button_intel = ctk.CTkButton(self.sidebar_frame, text="🧠 Run Intelligence", 
                                                 height=32, font=ctk.CTkFont(size=12),
                                                 fg_color="#7c3aed", hover_color="#6d28d9",
                                                 command=self.run_intelligence_event)
        self.sidebar_button_intel.grid(row=4, column=0, padx=20, pady=10)

        self.sidebar_button_clear = ctk.CTkButton(self.sidebar_frame, text="Clear Console", 
                                                 height=32, font=ctk.CTkFont(size=12),
                                                 fg_color="transparent", border_width=1, border_color="#334155",
                                                 command=self.clear_logs)
        self.sidebar_button_clear.grid(row=5, column=0, padx=20, pady=10)

        # Bottom Sidebar Elements
        self.appearance_mode_label = ctk.CTkLabel(self.sidebar_frame, text="Interface Color:", anchor="w", font=ctk.CTkFont(size=11))
        self.appearance_mode_label.grid(row=8, column=0, padx=20, pady=(40, 0))
        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(self.sidebar_frame, values=["Dark", "Light"],
                                                            fg_color=CARD_BG, button_color=ACCENT_COLOR,
                                                            command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.grid(row=9, column=0, padx=20, pady=(10, 20))
        self.appearance_mode_optionemenu.set("Dark")

        self.version_label = ctk.CTkLabel(self.sidebar_frame, text="v6.0 - Review & Approval", font=ctk.CTkFont(size=10), text_color="gray")
        self.version_label.grid(row=11, column=0, pady=20)

        # --- Main View Container ---
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(1, weight=1)

        # Header Info
        self.header_frame = ctk.CTkFrame(self.main_container, fg_color=CARD_BG, height=80, corner_radius=15)
        self.header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        
        self.channel_name_label = ctk.CTkLabel(self.header_frame, text="Channel: Connecting...", font=ctk.CTkFont(size=20, weight="bold"))
        self.channel_name_label.pack(side="left", padx=30, pady=15)
        
        self.subscriber_label = ctk.CTkLabel(self.header_frame, text="-- Subscribers", font=ctk.CTkFont(size=15), text_color="#94a3b8")
        self.subscriber_label.pack(side="left", padx=10, pady=15)

        self.status_indicator = ctk.CTkLabel(self.header_frame, text="● IDLE", text_color=SUCCESS_COLOR, font=ctk.CTkFont(size=14, weight="bold"))
        self.status_indicator.pack(side="right", padx=30, pady=15)

        # --- Tab View ---
        self.tabview = ctk.CTkTabview(self.main_container, corner_radius=15, fg_color=CARD_BG, segmented_button_selected_color=ACCENT_COLOR)
        self.tabview.grid(row=1, column=0, sticky="nsew")
        self.tabview.add("📊 Dashboard")
        self.tabview.add("⚡ Control Center")
        self.tabview.add("📝 Script Review")
        self.tabview.add("🎬 Review & Approve")
        self.tabview.add("📋 Logs")
        self.tabview.add("🧠 Learning Stats")
        
        # Build Tabs
        self._build_dashboard_tab()
        self._build_control_tab()
        self._build_script_review_tab()
        self._build_review_approve_tab()
        self._build_logs_tab()
        self._build_learning_tab()

        # Console Director
        self.director = ConsoleDirector(self.log_textbox)
        sys.stdout = self.director
        
        self.scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        self.update_dashboard()
        self.auto_refresh_loop()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 DSA Coding Studio initialized with Mandatory Review & Approval Gate.")

    # ── Dashboard Tab ────────────────────────────────────────────────────────
    def _build_dashboard_tab(self):
        self.tab_dash = self.tabview.tab("📊 Dashboard")
        self.tab_dash.grid_columnconfigure(0, weight=1)
        self.tab_dash.grid_rowconfigure(1, weight=1)

        self.stats_grid = ctk.CTkFrame(self.tab_dash, fg_color="transparent")
        self.stats_grid.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.stats_grid.grid_columnconfigure((0,1,2,3), weight=1)

        def create_stat_card(parent, title, color):
            card = ctk.CTkFrame(parent, fg_color="#1e293b", border_width=1, border_color="#334155", corner_radius=12)
            lbl_title = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=13), text_color="#94a3b8")
            lbl_title.pack(pady=(15, 0))
            lbl_val = ctk.CTkLabel(card, text="0", font=ctk.CTkFont(size=26, weight="bold"), text_color=color)
            lbl_val.pack(pady=(5, 15))
            return lbl_val

        self.total_uploads_val = create_stat_card(self.stats_grid, "TOTAL UPLOADS", "#f8fafc")
        self.total_uploads_val.master.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        self.total_views_val = create_stat_card(self.stats_grid, "TOTAL VIEWS", "#38bdf8")
        self.total_views_val.master.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        self.total_likes_val = create_stat_card(self.stats_grid, "TOTAL LIKES", "#4ade80")
        self.total_likes_val.master.grid(row=0, column=2, padx=10, pady=10, sticky="ew")

        self.quota_val = create_stat_card(self.stats_grid, "DAILY QUOTA", WARNING_COLOR)
        self.quota_val.master.grid(row=0, column=3, padx=10, pady=10, sticky="ew")

        self.video_scroll = ctk.CTkScrollableFrame(self.tab_dash, label_text="Recent Content Performance", 
                                                 fg_color="#0f172a", label_font=ctk.CTkFont(weight="bold"))
        self.video_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

    # ── Control Center Tab ───────────────────────────────────────────────────
    def _build_control_tab(self):
        self.tab_ctrl = self.tabview.tab("⚡ Control Center")
        self.tab_ctrl.grid_columnconfigure(0, weight=1)
        self.tab_ctrl.grid_rowconfigure(1, weight=1)

        self.input_frame = ctk.CTkFrame(self.tab_ctrl, fg_color="#1e293b", corner_radius=10)
        self.input_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        self.topic_entry = ctk.CTkEntry(self.input_frame, placeholder_text="e.g. Binary Search, DP on Trees, Graph BFS/DFS", 
                                       width=400, height=40, border_width=1, fg_color="#0f172a")
        self.topic_entry.pack(side="left", padx=20, pady=15)

        def get_niche_files():
            n_dir = "niches"
            if not os.path.exists(n_dir): return ["coding.yaml"]
            files = [f for f in os.listdir(n_dir) if f.endswith(".yaml")]
            return sorted(files) if files else ["coding.yaml"]
            
        self.niche_var = ctk.StringVar(value="coding.yaml")
        self.niche_menu = ctk.CTkOptionMenu(self.input_frame, variable=self.niche_var, values=get_niche_files(), 
                                           height=40, fg_color="#334155", button_color=ACCENT_COLOR)
        self.niche_menu.pack(side="left", padx=10)

        self.video_type_var = ctk.StringVar(value="short")
        self.short_radio = ctk.CTkRadioButton(self.input_frame, text="⚡ Short (60s)",
                                              variable=self.video_type_var, value="short",
                                              fg_color=ACCENT_COLOR, font=ctk.CTkFont(size=12))
        self.short_radio.pack(side="left", padx=8)

        self.stop_btn = ctk.CTkButton(self.input_frame, text="Force Stop ⏹", width=120, height=40,
                                     fg_color="#b91c1c", hover_color="#991b1b", font=ctk.CTkFont(weight="bold"),
                                     command=self.stop_processes_event)
        self.stop_btn.pack(side="right", padx=20)

        self.log_textbox = ctk.CTkTextbox(self.tab_ctrl, state="disabled", fg_color="#020617", 
                                         text_color="#94a3b8", font=ctk.CTkFont(family="Cascadia Code", size=12),
                                         border_width=1, border_color="#1e293b")
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

    # ── Script Review Tab ────────────────────────────────────────────────────
    def _build_script_review_tab(self):
        self.tab_script = self.tabview.tab("📝 Script Review")
        self.tab_script.grid_columnconfigure(1, weight=1)
        self.tab_script.grid_rowconfigure(0, weight=1)

        # Left Queue
        self.script_queue_frame = ctk.CTkScrollableFrame(self.tab_script, label_text="Scripts for Review", width=240, fg_color="#0f172a")
        self.script_queue_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)

        # Main Panel
        self.script_main_frame = ctk.CTkFrame(self.tab_script, fg_color=CARD_BG, corner_radius=10)
        self.script_main_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        self.script_main_frame.grid_columnconfigure(0, weight=1)
        self.script_main_frame.grid_rowconfigure(1, weight=1)

        # Header
        self.script_header_lbl = ctk.CTkLabel(self.script_main_frame, text="Select a script from the queue on the left", font=ctk.CTkFont(size=16, weight="bold"))
        self.script_header_lbl.grid(row=0, column=0, padx=20, pady=15, sticky="w")

        # Scrollable Beats Container
        self.script_beats_scroll = ctk.CTkScrollableFrame(self.script_main_frame, fg_color="#0f172a")
        self.script_beats_scroll.grid(row=1, column=0, sticky="nsew", padx=15, pady=10)
        self.script_beat_widgets = []

        # Action Buttons Bar
        self.script_action_bar = ctk.CTkFrame(self.script_main_frame, fg_color="transparent")
        self.script_action_bar.grid(row=2, column=0, sticky="ew", padx=15, pady=15)

        self.btn_save_script = ctk.CTkButton(self.script_action_bar, text="Save Script Draft 💾", fg_color="#334155", hover_color="#475569", command=self.save_script_draft_event)
        self.btn_save_script.pack(side="left", padx=5)

        self.btn_approve_script = ctk.CTkButton(self.script_action_bar, text="Approve & Render All 🚀", fg_color=ACCENT_COLOR, hover_color="#4f46e5", font=ctk.CTkFont(weight="bold"), command=self.approve_script_event)
        self.btn_approve_script.pack(side="right", padx=5)

    # ── Review & Approve Tab ─────────────────────────────────────────────────
    def _build_review_approve_tab(self):
        self.tab_review = self.tabview.tab("🎬 Review & Approve")
        self.tab_review.grid_columnconfigure(1, weight=1)
        self.tab_review.grid_rowconfigure(0, weight=1)

        # Left Queue Frame
        self.review_queue_frame = ctk.CTkScrollableFrame(self.tab_review, label_text="Pending Approval Queue", width=250, fg_color="#0f172a")
        self.review_queue_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)

        # Right Main Panel
        self.review_main_frame = ctk.CTkFrame(self.tab_review, fg_color=CARD_BG, corner_radius=10)
        self.review_main_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        self.review_main_frame.grid_columnconfigure((0, 1), weight=1)
        self.review_main_frame.grid_rowconfigure(1, weight=1)

        # Top Section: Video Preview + Metadata
        self.preview_container = ctk.CTkFrame(self.review_main_frame, fg_color="#0f172a", height=280)
        self.preview_container.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.lbl_preview_title = ctk.CTkLabel(self.preview_container, text="📹 Video Preview", font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_preview_title.pack(pady=5)

        self.btn_open_external_player = ctk.CTkButton(self.preview_container, text="▶️ Play Video", fg_color="#dc2626", hover_color="#b91c1c", command=self.play_video_event)
        self.btn_open_external_player.pack(pady=20)

        # Metadata Editor
        self.metadata_container = ctk.CTkScrollableFrame(self.review_main_frame, label_text="Metadata & YouTube Details", fg_color="#0f172a")
        self.metadata_container.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(self.metadata_container, text="Title:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10)
        self.entry_meta_title = ctk.CTkEntry(self.metadata_container, width=350)
        self.entry_meta_title.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(self.metadata_container, text="Description:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10)
        self.txt_meta_desc = ctk.CTkTextbox(self.metadata_container, height=70)
        self.txt_meta_desc.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(self.metadata_container, text="Tags (comma-separated):", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=10)
        self.entry_meta_tags = ctk.CTkEntry(self.metadata_container, width=350)
        self.entry_meta_tags.pack(fill="x", padx=10, pady=(0, 10))

        # Middle Section: Timeline & Tools
        self.timeline_tools_frame = ctk.CTkFrame(self.review_main_frame, fg_color="#0f172a")
        self.timeline_tools_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)
        self.timeline_tools_frame.grid_columnconfigure(0, weight=1)

        # Interactive Canvas Timeline
        self.lbl_timeline_title = ctk.CTkLabel(self.timeline_tools_frame, text="🎞️ Interactive Beat Timeline (Drag to trim/inspect)", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_timeline_title.pack(anchor="w", padx=10, pady=(5, 0))

        self.timeline_canvas = tk.Canvas(self.timeline_tools_frame, height=70, bg="#020617", highlightthickness=1, highlightbackground="#334155")
        self.timeline_canvas.pack(fill="x", padx=10, pady=5)

        # Tools Sub-bar
        self.tools_sub_bar = ctk.CTkFrame(self.timeline_tools_frame, fg_color="transparent")
        self.tools_sub_bar.pack(fill="x", padx=10, pady=5)

        self.btn_reassemble = ctk.CTkButton(self.tools_sub_bar, text="Reassemble Timeline ✂️", fg_color="#334155", hover_color="#475569", command=self.reassemble_timeline_event)
        self.btn_reassemble.pack(side="left", padx=5)

        self.music_var = ctk.StringVar(value="Select Music Track")
        self.music_dropdown = ctk.CTkOptionMenu(self.tools_sub_bar, variable=self.music_var, values=self.get_music_files())
        self.music_dropdown.pack(side="left", padx=5)

        self.btn_swap_music = ctk.CTkButton(self.tools_sub_bar, text="Swap Music 🎵", fg_color="#334155", hover_color="#475569", command=self.swap_music_event)
        self.btn_swap_music.pack(side="left", padx=5)

        self.btn_regen_captions = ctk.CTkButton(self.tools_sub_bar, text="Regenerate Captions 💬", fg_color="#334155", hover_color="#475569", command=self.regenerate_captions_event)
        self.btn_regen_captions.pack(side="right", padx=5)

        # Bottom Action Buttons
        self.review_action_bar = ctk.CTkFrame(self.review_main_frame, fg_color="transparent")
        self.review_action_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=15, pady=15)

        self.btn_save_draft_review = ctk.CTkButton(self.review_action_bar, text="Save Draft 💾", fg_color="#334155", command=self.save_review_draft_event)
        self.btn_save_draft_review.pack(side="left", padx=5)

        self.btn_reject_review = ctk.CTkButton(self.review_action_bar, text="Reject ❌", fg_color="#b91c1c", hover_color="#991b1b", command=self.reject_video_event)
        self.btn_reject_review.pack(side="left", padx=5)

        self.btn_approve_upload = ctk.CTkButton(self.review_action_bar, text="Approve & Upload to YouTube 🚀", fg_color=SUCCESS_COLOR, hover_color="#059669", font=ctk.CTkFont(weight="bold", size=14), command=self.approve_and_upload_event)
        self.btn_approve_upload.pack(side="right", padx=5)

    def get_music_files(self):
        m_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media", "music")
        if not os.path.exists(m_dir): return ["No tracks found"]
        files = [f for f in os.listdir(m_dir) if f.endswith(".mp3") or f.endswith(".wav")]
        return files if files else ["No tracks found"]

    # ── System Logs Tab ──────────────────────────────────────────────────────
    def _build_logs_tab(self):
        self.tab_logs = self.tabview.tab("📋 Logs")
        self.tab_logs.grid_columnconfigure(0, weight=1)
        self.tab_logs.grid_rowconfigure(1, weight=1)

        # Filters Bar
        self.logs_filter_bar = ctk.CTkFrame(self.tab_logs, fg_color="#1e293b", corner_radius=8)
        self.logs_filter_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        ctk.CTkLabel(self.logs_filter_bar, text="Stage:").pack(side="left", padx=(15, 5), pady=10)
        self.log_stage_var = ctk.StringVar(value="ALL")
        self.log_stage_dropdown = ctk.CTkOptionMenu(self.logs_filter_bar, variable=self.log_stage_var, values=["ALL", "TREND_SCRAPE", "SCRIPT_GEN", "BEAT_RENDER", "TTS", "ASSEMBLY", "HEALTH_CHECK", "UPLOAD", "EDIT", "STATE_TRANSITION"], command=lambda _: self.refresh_logs_table())
        self.log_stage_dropdown.pack(side="left", padx=5)

        ctk.CTkLabel(self.logs_filter_bar, text="Level:").pack(side="left", padx=(15, 5), pady=10)
        self.log_level_var = ctk.StringVar(value="ALL")
        self.log_level_dropdown = ctk.CTkOptionMenu(self.logs_filter_bar, variable=self.log_level_var, values=["ALL", "INFO", "WARNING", "ERROR"], command=lambda _: self.refresh_logs_table())
        self.log_level_dropdown.pack(side="left", padx=5)

        self.btn_export_csv = ctk.CTkButton(self.logs_filter_bar, text="Export CSV 📥", fg_color="#334155", hover_color="#475569", command=self.export_logs_csv_event)
        self.btn_export_csv.pack(side="right", padx=15)

        self.btn_refresh_logs = ctk.CTkButton(self.logs_filter_bar, text="Refresh 🔄", fg_color=ACCENT_COLOR, command=self.refresh_logs_table)
        self.btn_refresh_logs.pack(side="right", padx=5)

        # Table View Container using ttk.Treeview
        self.logs_tree_frame = ctk.CTkFrame(self.tab_logs, fg_color="#020617")
        self.logs_tree_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.logs_tree_frame.grid_columnconfigure(0, weight=1)
        self.logs_tree_frame.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#0f172a", foreground="#f8fafc", fieldbackground="#0f172a", rowheight=25)
        style.configure("Treeview.Heading", background="#1e293b", foreground="#38bdf8", font=("Inter", 10, "bold"))
        style.map("Treeview", background=[("selected", ACCENT_COLOR)])

        columns = ("id", "timestamp", "pipeline_id", "stage", "level", "duration", "message")
        self.logs_tree = ttk.Treeview(self.logs_tree_frame, columns=columns, show="headings", selectmode="browse")

        self.logs_tree.heading("id", text="ID")
        self.logs_tree.heading("timestamp", text="Timestamp")
        self.logs_tree.heading("pipeline_id", text="Pipeline ID")
        self.logs_tree.heading("stage", text="Stage")
        self.logs_tree.heading("level", text="Level")
        self.logs_tree.heading("duration", text="Duration (ms)")
        self.logs_tree.heading("message", text="Message")

        self.logs_tree.column("id", width=50, anchor="center")
        self.logs_tree.column("timestamp", width=140, anchor="center")
        self.logs_tree.column("pipeline_id", width=80, anchor="center")
        self.logs_tree.column("stage", width=120, anchor="center")
        self.logs_tree.column("level", width=80, anchor="center")
        self.logs_tree.column("duration", width=100, anchor="center")
        self.logs_tree.column("message", width=450, anchor="w")

        scrollbar = ttk.Scrollbar(self.logs_tree_frame, orient="vertical", command=self.logs_tree.yview)
        self.logs_tree.configure(yscrollcommand=scrollbar.set)

        self.logs_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    # ── Learning Stats Tab ───────────────────────────────────────────────────
    def _build_learning_tab(self):
        self.tab_learn = self.tabview.tab("🧠 Learning Stats")
        self.tab_learn.grid_columnconfigure((0, 1), weight=1)
        self.tab_learn.grid_rowconfigure(0, weight=1)

        self.left_learn_frame = ctk.CTkScrollableFrame(self.tab_learn, label_text="System Preferences & Optimization", fg_color="#0f172a")
        self.left_learn_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.right_learn_frame = ctk.CTkScrollableFrame(self.tab_learn, label_text="Visual Sequences & Keywords", fg_color="#0f172a")
        self.right_learn_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        self.learn_control_bar = ctk.CTkFrame(self.tab_learn, fg_color="transparent")
        self.learn_control_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        
        self.manual_sync_btn = ctk.CTkButton(self.learn_control_bar, text="Manual Sync & Recompute 🔄", 
                                             height=40, font=ctk.CTkFont(weight="bold"),
                                             fg_color="#7c3aed", hover_color="#6d28d9",
                                             command=self.manual_sync_recompute_event)
        self.manual_sync_btn.pack(pady=10)

    # ── Auto Refresh Loop & Event Handlers ───────────────────────────────────
    def auto_refresh_loop(self):
        try:
            self.update_dashboard()
            self.refresh_script_queue()
            self.refresh_review_queue()
            if self.live_log_tail:
                self.refresh_logs_table()
        except Exception:
            pass
        self.after(3000, self.auto_refresh_loop)

    def update_dashboard(self):
        if not hasattr(self, '_channel_stats_fetched'):
            self._channel_stats_fetched = True
            def fetch_chan():
                stats = get_channel_stats()
                if stats:
                    self.after(0, lambda: self.channel_name_label.configure(text=f"Channel: {stats['name']}"))
                    self.after(0, lambda: self.subscriber_label.configure(text=f"{stats['subscribers']:,} Subscribers"))
            threading.Thread(target=fetch_chan, daemon=True).start()

        conn = sqlite3.connect(database.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(views), SUM(likes) FROM videos")
        total_count, total_views, total_likes = cursor.fetchone()
        
        self.total_uploads_val.configure(text=str(total_count or 0))
        self.total_views_val.configure(text=str(total_views or 0))
        self.total_likes_val.configure(text=str(total_likes or 0))

        today_count = database.get_todays_video_count()
        self.quota_val.configure(text=f"{today_count}/{DAILY_VIDEO_LIMIT}")
        self.quota_val.configure(text_color=ERROR_COLOR if today_count >= DAILY_VIDEO_LIMIT else WARNING_COLOR)

        for widget in self.video_scroll.winfo_children(): widget.destroy()
        cursor.execute("SELECT video_id, title, niche, views, likes, comments, upload_time FROM videos ORDER BY upload_time DESC LIMIT 30")
        for i, (vid, title, niche, views, likes, comments, utime) in enumerate(cursor.fetchall()):
            row = ctk.CTkFrame(self.video_scroll, fg_color="#1e293b" if i % 2 == 0 else "transparent", corner_radius=8)
            row.pack(fill="x", padx=10, pady=2)
            
            ctk.CTkLabel(row, text=utime[:10], width=80, text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left", padx=10)
            ctk.CTkLabel(row, text=f"{title[:45]}...", width=280, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
            
            eng_rate = ((likes + comments) / views * 100) if views else 0
            
            watch_btn = ctk.CTkButton(row, text="Play", width=50, height=24, fg_color="#dc2626", hover_color="#991b1b",
                                     command=lambda v=vid: webbrowser.open(f"https://youtu.be/{v}"))
            watch_btn.pack(side="right", padx=15, pady=5)
            
            ctk.CTkLabel(row, text=f"{eng_rate:.1f}%", width=50, text_color="#a855f7").pack(side="right", padx=5)
            ctk.CTkLabel(row, text=f"❤️ {likes}", width=60, text_color=SUCCESS_COLOR).pack(side="right", padx=5)
            ctk.CTkLabel(row, text=f"👁️ {views}", width=60, text_color="#38bdf8").pack(side="right", padx=5)
        conn.close()

    # ── Script Review Helpers ────────────────────────────────────────────────
    def refresh_script_queue(self):
        for widget in self.script_queue_frame.winfo_children():
            widget.destroy()

        conn = sqlite3.connect(database.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, topic, status FROM video_pipeline WHERE status IN ('SCRIPT_REVIEW', 'SCRIPT_GENERATED', 'DRAFT') ORDER BY id ASC")
        rows = c.fetchall()
        conn.close()

        for row in rows:
            pid = row["id"]
            topic = row["topic"]
            status = row["status"]

            btn = ctk.CTkButton(
                self.script_queue_frame,
                text=f"#{pid}: {topic[:22]}...\n[{status}]",
                height=45,
                fg_color=ACCENT_COLOR if pid == self.selected_script_pipeline_id else "#1e293b",
                command=lambda p=pid: self.load_script_pipeline(p)
            )
            btn.pack(fill="x", padx=5, pady=4)

    def load_script_pipeline(self, pipeline_id):
        self.selected_script_pipeline_id = pipeline_id
        self.refresh_script_queue()

        data = script_review_manager.get_script_for_review(pipeline_id)
        pipeline = data["pipeline"]
        beats = data["beats"]

        self.script_header_lbl.configure(text=f"Pipeline #{pipeline_id}: {pipeline['topic']} [{pipeline['status']}]")

        for widget in self.script_beats_scroll.winfo_children():
            widget.destroy()
        self.script_beat_widgets = []

        for idx, beat in enumerate(beats):
            card = ctk.CTkFrame(self.script_beats_scroll, fg_color="#1e293b", corner_radius=8)
            card.pack(fill="x", padx=10, pady=5)

            lbl_title = ctk.CTkLabel(card, text=f"Beat {idx+1} — Action: {beat.get('visual_action', 'text_only')}", font=ctk.CTkFont(size=12, weight="bold"), text_color="#38bdf8")
            lbl_title.pack(anchor="w", padx=10, pady=(5, 2))

            entry_text = ctk.CTkEntry(card, width=500)
            entry_text.insert(0, beat.get("text", ""))
            entry_text.pack(fill="x", padx=10, pady=5)

            btn_single_regen = ctk.CTkButton(card, text="Regenerate Beat ↻", width=120, height=26, fg_color="#334155", command=lambda b_idx=idx, e=entry_text: self.regen_single_beat_event(pipeline_id, b_idx, e.get()))
            btn_single_regen.pack(anchor="e", padx=10, pady=(0, 5))

            self.script_beat_widgets.append({"index": idx, "entry": entry_text, "beat": beat})

    def regen_single_beat_event(self, pipeline_id, beat_index, text):
        def run():
            beat_data = self.script_beat_widgets[beat_index]["beat"]
            beat_data["text"] = text
            res = beat_renderer.render_single_beat(pipeline_id, beat_index, beat_data)
            if res:
                print(f"✅ Beat {beat_index} re-rendered successfully.")
            else:
                print(f"❌ Single beat {beat_index} re-render failed.")
        threading.Thread(target=run, daemon=True).start()

    def save_script_draft_event(self):
        if not self.selected_script_pipeline_id:
            return
        updated_beats = []
        for w in self.script_beat_widgets:
            b = dict(w["beat"])
            b["text"] = w["entry"].get()
            updated_beats.append(b)

        ver = script_review_manager.save_script_edit(self.selected_script_pipeline_id, updated_beats, edit_note="Edited in GUI")
        messagebox.showinfo("Script Saved", f"Saved script draft version v{ver}.")

    def approve_script_event(self):
        if not self.selected_script_pipeline_id:
            return
        self.save_script_draft_event()
        pid = self.selected_script_pipeline_id
        script_review_manager.approve_script(pid)
        print(f"🚀 Script #{pid} approved. Starting render worker...")

        def run_render():
            p = database.get_pipeline(pid)
            from render_worker import _render_single_job
            _render_single_job({"topic": p["topic"], "niche_file": "coding.yaml", "pipeline_id": pid, "phase": "render_video"})
            self.after(0, self.refresh_script_queue)
            self.after(0, self.refresh_review_queue)

        threading.Thread(target=run_render, daemon=True).start()

    # ── Review & Approve Helpers ─────────────────────────────────────────────
    def refresh_review_queue(self):
        for widget in self.review_queue_frame.winfo_children():
            widget.destroy()

        conn = sqlite3.connect(database.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, topic, status FROM video_pipeline WHERE status IN ('PENDING_REVIEW', 'NEEDS_REGENERATION', 'RENDERED') ORDER BY id ASC")
        rows = c.fetchall()
        conn.close()

        for row in rows:
            pid = row["id"]
            topic = row["topic"]
            status = row["status"]

            btn = ctk.CTkButton(
                self.review_queue_frame,
                text=f"#{pid}: {topic[:22]}...\n[{status}]",
                height=45,
                fg_color=SUCCESS_COLOR if pid == self.selected_review_pipeline_id else "#1e293b",
                command=lambda p=pid: self.load_review_pipeline(p)
            )
            btn.pack(fill="x", padx=5, pady=4)

    def load_review_pipeline(self, pipeline_id):
        self.selected_review_pipeline_id = pipeline_id
        self.refresh_review_queue()

        p = database.get_pipeline(pipeline_id)
        if not p: return

        self.entry_meta_title.delete(0, "end")
        self.entry_meta_title.insert(0, p.get("title") or p["topic"])

        self.txt_meta_desc.delete("1.0", "end")
        self.txt_meta_desc.insert("1.0", p.get("description") or "")

        self.entry_meta_tags.delete(0, "end")
        self.entry_meta_tags.insert(0, p.get("tags") or "")

        # Render timeline canvas
        self.draw_timeline_canvas(pipeline_id)

    def play_video_event(self):
        if not self.selected_review_pipeline_id: return
        p = database.get_pipeline(self.selected_review_pipeline_id)
        if p and p.get("video_path") and os.path.exists(p["video_path"]):
            webbrowser.open(f"file://{os.path.abspath(p['video_path'])}")
        else:
            messagebox.showerror("Error", "Video file not found.")

    def draw_timeline_canvas(self, pipeline_id):
        self.timeline_canvas.delete("all")

        conn = sqlite3.connect(database.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM beat_versions WHERE pipeline_id = ? AND is_current = 1 ORDER BY beat_index ASC", (pipeline_id,))
        beats = c.fetchall()
        conn.close()

        if not beats:
            self.timeline_canvas.create_text(200, 35, text="No beat timeline rendered yet", fill="gray")
            return

        total_dur = sum(b.get("duration_seconds") or 4.0 for b in beats)
        canvas_width = self.timeline_canvas.winfo_width() or 600

        x_cursor = 10
        colors = ["#6366f1", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#14b8a6"]

        for idx, b in enumerate(beats):
            dur = b.get("duration_seconds") or 4.0
            block_w = max(50, int((dur / total_dur) * (canvas_width - 40)))
            color = colors[idx % len(colors)]

            self.timeline_canvas.create_rectangle(x_cursor, 10, x_cursor + block_w, 60, fill=color, outline="#ffffff")
            self.timeline_canvas.create_text(x_cursor + block_w/2, 35, text=f"B{b['beat_index']+1}\n{dur:.1f}s", fill="#ffffff", font=("Inter", 9, "bold"))
            x_cursor += block_w + 5

    def reassemble_timeline_event(self):
        if not self.selected_review_pipeline_id: return
        pid = self.selected_review_pipeline_id

        conn = sqlite3.connect(database.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT beat_index, duration_seconds FROM beat_versions WHERE pipeline_id = ? AND is_current = 1 ORDER BY beat_index ASC", (pid,))
        rows = c.fetchall()
        conn.close()

        spec = [{"beat_index": r[0], "trim_start": 0.0, "trim_end": r[1], "include": True} for r in rows]

        def run():
            out = video_editor.reassemble_from_timeline(pid, spec)
            if out:
                print(f"✅ Timeline reassembled: {out}")
            else:
                print("❌ Timeline reassembly failed.")
        threading.Thread(target=run, daemon=True).start()

    def swap_music_event(self):
        if not self.selected_review_pipeline_id: return
        track = self.music_var.get()
        if track == "Select Music Track" or track == "No tracks found":
            messagebox.showwarning("Warning", "Select a valid music track.")
            return

        m_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media", "music", track)
        pid = self.selected_review_pipeline_id

        def run():
            out = video_editor.swap_background_music(pid, m_path)
            if out: print(f"✅ Music swapped to {track}")
        threading.Thread(target=run, daemon=True).start()

    def regenerate_captions_event(self):
        if not self.selected_review_pipeline_id: return
        pid = self.selected_review_pipeline_id

        p = database.get_pipeline(pid)
        if not p or not p.get("script_json"): return

        beats = json.loads(p["script_json"])
        lines = []
        cur = 0.0
        for b in beats:
            dur = 4.0
            lines.append({"text": b.get("text", ""), "start_sec": cur, "end_sec": cur + dur})
            cur += dur

        def run():
            out = video_editor.regenerate_captions(pid, lines)
            if out: print(f"✅ Captions updated: {out}")
        threading.Thread(target=run, daemon=True).start()

    def save_review_draft_event(self):
        if not self.selected_review_pipeline_id: return
        pid = self.selected_review_pipeline_id
        database.update_pipeline_status(
            pid,
            status=PipelineStatus.PENDING_REVIEW.value,
            title=self.entry_meta_title.get(),
            description=self.txt_meta_desc.get("1.0", "end-1c"),
            tags=self.entry_meta_tags.get()
        )
        messagebox.showinfo("Saved", "Draft changes saved.")

    def reject_video_event(self):
        if not self.selected_review_pipeline_id: return
        pid = self.selected_review_pipeline_id
        reason = ctk.CTkInputDialog(text="Enter rejection reason:", title="Reject Video").get_input()
        if reason:
            transition(pid, PipelineStatus.REJECTED, note=reason)
            transition(pid, PipelineStatus.SCRIPT_REVIEW)
            messagebox.showinfo("Rejected", f"Pipeline #{pid} routed back to Script Review.")
            self.refresh_review_queue()
            self.refresh_script_queue()

    def approve_and_upload_event(self):
        if not self.selected_review_pipeline_id: return
        pid = self.selected_review_pipeline_id

        # Save latest metadata changes first
        database.update_pipeline_status(
            pid,
            status=PipelineStatus.PENDING_REVIEW.value,
            title=self.entry_meta_title.get(),
            description=self.txt_meta_desc.get("1.0", "end-1c"),
            tags=self.entry_meta_tags.get()
        )

        transition(pid, PipelineStatus.APPROVED)
        print(f"✅ Pipeline #{pid} APPROVED by human operator! Initiating YouTube upload...")

        def run_upload():
            p = database.get_pipeline(pid)
            tags_list = [t.strip() for t in p.get("tags", "").split(",") if t.strip()]
            try:
                vid_id = upload_video(
                    video_path=p["video_path"],
                    title=p["title"],
                    description=p["description"],
                    tags=tags_list,
                    pipeline_id=pid
                )
                if vid_id:
                    print(f"🎉 Upload Complete! Video ID: {vid_id}")
            except Exception as e:
                print(f"❌ Upload Error: {e}")
            self.after(0, self.refresh_review_queue)

        threading.Thread(target=run_upload, daemon=True).start()

    # ── Logs Helpers ─────────────────────────────────────────────────────────
    def refresh_logs_table(self):
        for item in self.logs_tree.get_children():
            self.logs_tree.delete(item)

        st_filter = self.log_stage_var.get()
        lvl_filter = self.log_level_var.get()

        stage = None if st_filter == "ALL" else st_filter
        level = None if lvl_filter == "ALL" else lvl_filter

        logs = database.get_pipeline_logs(stage=stage, level=level)

        for l in logs:
            self.logs_tree.insert(
                "",
                "end",
                values=(
                    l["id"],
                    l["created_at"][:19] if l.get("created_at") else "",
                    l.get("pipeline_id") or "-",
                    l["stage"],
                    l["level"],
                    l.get("duration_ms") or "-",
                    l["message"][:80]
                )
            )

    def export_logs_csv_event(self):
        logs = database.get_pipeline_logs()
        if not logs:
            messagebox.showinfo("Export CSV", "No logs to export.")
            return

        export_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline_logs_export.csv")
        with open(export_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=logs[0].keys())
            writer.writeheader()
            writer.writerows(logs)

        messagebox.showinfo("Export CSV", f"Exported {len(logs)} logs to:\n{export_file}")

    # ── Miscellaneous Controls ──────────────────────────────────────────────
    def run_now_event(self):
        topic = self.topic_entry.get().strip()
        niche = self.niche_var.get()

        self.status_indicator.configure(text="● RUNNING", text_color=WARNING_COLOR)
        self.sidebar_button_run.configure(state="disabled")
        
        def run_task():
            try:
                job(manual_topic=topic, manual_niche=niche) if topic else job()
                self.after(0, self.update_dashboard)
            finally:
                self.after(0, lambda: self.status_indicator.configure(text="● IDLE", text_color=SUCCESS_COLOR))
                self.after(0, lambda: self.sidebar_button_run.configure(state="normal"))
                self.after(0, lambda: self.topic_entry.delete(0, 'end'))
        threading.Thread(target=run_task, daemon=True).start()

    def sync_stats_event(self):
        self.sidebar_button_sync.configure(state="disabled", text="Syncing...")
        def run_sync():
            try:
                database.sync_all_video_stats()
                self.after(0, self.update_dashboard)
            finally:
                self.after(0, lambda: self.sidebar_button_sync.configure(state="normal", text="Sync Metrics 🔄"))
        threading.Thread(target=run_sync, daemon=True).start()

    def manual_sync_recompute_event(self):
        self.manual_sync_btn.configure(state="disabled", text="Syncing & Re-computing...")
        def run_sync_recompute():
            try:
                print("\n🔄 Starting YouTube Analytics Sync and re-computing weights...")
                from analytics_sync import run_analytics_sync
                run_analytics_sync()
                print("✅ Sync and recomputation complete.")
                self.after(0, self.update_dashboard)
            except Exception as e:
                print(f"❌ Error during manual sync/recompute: {e}")
            finally:
                self.after(0, lambda: self.manual_sync_btn.configure(state="normal", text="Manual Sync & Recompute 🔄"))
        threading.Thread(target=run_sync_recompute, daemon=True).start()

    def run_intelligence_event(self):
        self.sidebar_button_intel.configure(state="disabled", text="🧠 Analyzing...")
        def run_intel():
            try:
                from youtube_intelligence import seed_intelligent_topics, get_intelligence_report
                count = seed_intelligent_topics()
                report = get_intelligence_report()
                print(f"\n🧠 Intelligence Run Complete — {count} new topics added")
                print(report)
                self.after(0, self.update_dashboard)
            except Exception as e:
                print(f"[🧠 Intelligence] Error: {e}")
            finally:
                self.after(0, lambda: self.sidebar_button_intel.configure(state="normal", text="🧠 Run Intelligence"))
        threading.Thread(target=run_intel, daemon=True).start()

    def stop_processes_event(self):
        import subprocess
        subprocess.run(["pkill", "-f", "main.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "ffmpeg"], capture_output=True)
        subprocess.run(["pkill", "-f", "manim"], capture_output=True)
        self.status_indicator.configure(text="● IDLE", text_color=SUCCESS_COLOR)
        self.sidebar_button_run.configure(state="normal")

    def clear_logs(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    def check_quota_event(self):
        quota_info = quota_manager.get_quota_info()
        print("\n" + "="*40 + "\n" + quota_info + "\n" + "="*40 + "\n")
        if messagebox.askyesno("Gemini Quota Limits", f"{quota_info}\n\nOpen AI Studio dashboard?"):
            quota_manager.open_ai_studio_dashboard()

    def change_appearance_mode_event(self, mode: str):
        ctk.set_appearance_mode(mode)

if __name__ == "__main__":
    app = App()
    app.mainloop()
