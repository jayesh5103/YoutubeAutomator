import os
import sys

# Auto-restart in virtual environment if not already running in one.
expected_venv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
if sys.prefix != expected_venv and os.path.exists(os.path.join(expected_venv, "bin", "python3")):
    print(f"🔄 Restarting gui.py within the project virtual environment ({expected_venv})...")
    os.execv(os.path.join(expected_venv, "bin", "python3"), [os.path.join(expected_venv, "bin", "python3")] + sys.argv)

import tkinter as tk
import customtkinter as ctk
import threading
import sys
import os
import queue
import webbrowser
from datetime import datetime

# Import our logic
from main import job, run_scheduler, DAILY_VIDEO_LIMIT
import quota_manager
import database
import sqlite3
from youtube_uploader import get_channel_stats

# --- Custom Theme/Colors ---
ACCENT_COLOR = "#6366f1"  # Indigo
SUCCESS_COLOR = "#10b981" # Emerald
WARNING_COLOR = "#f59e0b" # Amber
ERROR_COLOR = "#ef4444"   # Rose
BG_DARK = "#0f172a"       # Slate 900
CARD_BG = "#1e293b"       # Slate 800
SIDEBAR_BG = "#111827"    # Gray 900

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue") # We'll override mostly with manual colors

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
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", msg)
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")
        self.text_widget.after(100, self.update_widget)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI Coding Studio")
        self.geometry("1100x800")
        self.configure(fg_color=BG_DARK)

        # Grid configuration
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

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

        self.version_label = ctk.CTkLabel(self.sidebar_frame, text="v5.0 - AI Intelligence", font=ctk.CTkFont(size=10), text_color="gray")
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
        self.tabview.add("🧠 Learning Stats")
        
        # --- Dashboard Tab ---
        self.tab_dash = self.tabview.tab("📊 Dashboard")
        self.tab_dash.grid_columnconfigure(0, weight=1)
        self.tab_dash.grid_rowconfigure(1, weight=1)

        # Stats Grid (Cards)
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

        # Scrollable Video List
        self.video_scroll = ctk.CTkScrollableFrame(self.tab_dash, label_text="Recent Content Performance", 
                                                 fg_color="#0f172a", label_font=ctk.CTkFont(weight="bold"))
        self.video_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        # --- Control Center Tab ---
        self.tab_ctrl = self.tabview.tab("⚡ Control Center")
        self.tab_ctrl.grid_columnconfigure(0, weight=1)
        self.tab_ctrl.grid_rowconfigure(1, weight=1)

        # Manual Input Bar
        self.input_frame = ctk.CTkFrame(self.tab_ctrl, fg_color="#1e293b", corner_radius=10)
        self.input_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        self.topic_entry = ctk.CTkEntry(self.input_frame, placeholder_text="e.g. Binary Search, DP on Trees, Graph BFS/DFS", 
                                       width=400, height=40, border_width=1, fg_color="#0f172a")
        self.topic_entry.pack(side="left", padx=20, pady=15)

        def get_niche_files():
            n_dir = "niches"
            if not os.path.exists(n_dir): return ["tech.yaml"]
            files = [f for f in os.listdir(n_dir) if f.endswith(".yaml")]
            return sorted(files) if files else ["tech.yaml"]
            
        self.niche_var = ctk.StringVar(value="coding.yaml")
        self.niche_menu = ctk.CTkOptionMenu(self.input_frame, variable=self.niche_var, values=get_niche_files(), 
                                           height=40, fg_color="#334155", button_color=ACCENT_COLOR)
        self.niche_menu.pack(side="left", padx=10)

        self.video_type_var = ctk.StringVar(value="short")
        self.short_radio = ctk.CTkRadioButton(self.input_frame, text="⚡ Short (60s)",
                                              variable=self.video_type_var, value="short",
                                              fg_color=ACCENT_COLOR, font=ctk.CTkFont(size=12))
        self.short_radio.pack(side="left", padx=8)
        self.long_radio = ctk.CTkRadioButton(self.input_frame, text="🎬 Long (7-10 min)",
                                             variable=self.video_type_var, value="long",
                                             fg_color="#7c3aed", font=ctk.CTkFont(size=12))
        self.long_radio.pack(side="left", padx=8)

        self.stop_btn = ctk.CTkButton(self.input_frame, text="Force Stop ⏹", width=120, height=40,
                                     fg_color="#b91c1c", hover_color="#991b1b", font=ctk.CTkFont(weight="bold"),
                                     command=self.stop_processes_event)
        self.stop_btn.pack(side="right", padx=20)

        # Large Console
        self.log_textbox = ctk.CTkTextbox(self.tab_ctrl, state="disabled", fg_color="#020617", 
                                         text_color="#94a3b8", font=ctk.CTkFont(family="Cascadia Code", size=12),
                                         border_width=1, border_color="#1e293b")
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        # --- Learning Stats Tab UI ---
        self.tab_learn = self.tabview.tab("🧠 Learning Stats")
        self.tab_learn.grid_columnconfigure((0, 1), weight=1)
        self.tab_learn.grid_rowconfigure(0, weight=1)
        self.tab_learn.grid_rowconfigure(1, weight=0)

        # Left Column: General Preferences Card
        self.left_learn_frame = ctk.CTkScrollableFrame(self.tab_learn, label_text="System Preferences & Optimization", 
                                                       fg_color="#0f172a", label_font=ctk.CTkFont(weight="bold"))
        self.left_learn_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Right Column: Visual Sequences & Keywords Card
        self.right_learn_frame = ctk.CTkScrollableFrame(self.tab_learn, label_text="Visual Sequences & Keywords", 
                                                        fg_color="#0f172a", label_font=ctk.CTkFont(weight="bold"))
        self.right_learn_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        # Bottom Sync Button Bar
        self.learn_control_bar = ctk.CTkFrame(self.tab_learn, fg_color="transparent")
        self.learn_control_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        
        self.manual_sync_btn = ctk.CTkButton(self.learn_control_bar, text="Manual Sync & Recompute 🔄", 
                                             height=40, font=ctk.CTkFont(weight="bold"),
                                             fg_color="#7c3aed", hover_color="#6d28d9",
                                             command=self.manual_sync_recompute_event)
        self.manual_sync_btn.pack(pady=10)

        # --- Logic Integration ---
        self.director = ConsoleDirector(self.log_textbox)
        sys.stdout = self.director
        
        self.scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        self.update_dashboard()
        self.auto_refresh_loop()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 DSA Coding Studio initialized. Ready for content generation.")

    def auto_refresh_loop(self):
        try: self.update_dashboard()
        except: pass
        self.after(60000, self.auto_refresh_loop)

    def update_dashboard(self):
        # Channel Stats
        def fetch_chan():
            stats = get_channel_stats()
            if stats:
                self.after(0, lambda: self.channel_name_label.configure(text=f"Channel: {stats['name']}"))
                self.after(0, lambda: self.subscriber_label.configure(text=f"{stats['subscribers']:,} Subscribers"))
        threading.Thread(target=fetch_chan, daemon=True).start()

        # Database Stats
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

        # Video List
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
        
        # Update learning stats tab values
        try:
            self.update_learning_stats()
        except Exception as e:
            print(f"[GUI] Error updating learning stats UI: {e}")

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

    def update_learning_stats(self):
        import json
        # Clear frames
        for widget in self.left_learn_frame.winfo_children(): widget.destroy()
        for widget in self.right_learn_frame.winfo_children(): widget.destroy()
        
        conn = sqlite3.connect(database.DB_PATH)
        cursor = conn.cursor()
        
        # --- LEFT PANEL: General Preferences ---
        # 1. Script preferences
        cursor.execute("SELECT key, value, confidence FROM script_preferences")
        script_prefs = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
        
        # Display best hook style
        hook_style, hook_conf = script_prefs.get('best_hook_style', ('None (Cold Start)', 0.0))
        h_card = ctk.CTkFrame(self.left_learn_frame, fg_color=CARD_BG, corner_radius=8)
        h_card.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(h_card, text="Best Hook Style", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(anchor="w", padx=10, pady=2)
        ctk.CTkLabel(h_card, text=hook_style.replace('_', ' ').title(), font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10)
        ctk.CTkLabel(h_card, text=f"Confidence: {hook_conf:.2f}", font=ctk.CTkFont(size=10), text_color="#10b981" if hook_conf > 0.4 else "gray").pack(anchor="w", padx=10, pady=2)
        
        # Display pacing preferences
        pacing_pref, pacing_conf = script_prefs.get('pacing_preference', ('None (Cold Start)', 0.0))
        opt_min = script_prefs.get('optimal_beat_duration_min', ('4.0', 0.0))[0]
        opt_max = script_prefs.get('optimal_beat_duration_max', ('6.0', 0.0))[0]
        
        p_card = ctk.CTkFrame(self.left_learn_frame, fg_color=CARD_BG, corner_radius=8)
        p_card.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(p_card, text="Optimal Beat Pacing", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(anchor="w", padx=10, pady=2)
        ctk.CTkLabel(p_card, text=f"Range: {opt_min}s to {opt_max}s | Pacing: {pacing_pref.title()}", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10)
        ctk.CTkLabel(p_card, text=f"Confidence: {pacing_conf:.2f}", font=ctk.CTkFont(size=10), text_color="#10b981" if pacing_conf > 0.4 else "gray").pack(anchor="w", padx=10, pady=2)

        # 2. Upload preferences
        cursor.execute("SELECT key, value, confidence FROM upload_preferences")
        upload_prefs = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
        
        # Display best upload hour/day
        best_hr, hr_conf = upload_prefs.get('best_upload_hour', ('None', 0.0))
        best_day, day_conf = upload_prefs.get('best_upload_day', ('None', 0.0))
        
        days_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
        day_str = days_map.get(int(best_day), "None") if best_day != 'None' else 'None'
        hr_str = f"{int(best_hr):02d}:00" if best_hr != 'None' else 'None'
        
        u_card = ctk.CTkFrame(self.left_learn_frame, fg_color=CARD_BG, corner_radius=8)
        u_card.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(u_card, text="Best Upload Slot", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(anchor="w", padx=10, pady=2)
        ctk.CTkLabel(u_card, text=f"Day: {day_str} | Hour: {hr_str}", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10)
        ctk.CTkLabel(u_card, text=f"Confidence: {max(float(hr_conf), float(day_conf)):.2f}", font=ctk.CTkFont(size=10), text_color="#10b981" if max(float(hr_conf), float(day_conf)) > 0.4 else "gray").pack(anchor="w", padx=10, pady=2)

        # Title instructions
        title_inst = upload_prefs.get('best_title_template', ('Master [Topic Keyword] | [Catchy Hinglish Phrase] #Shorts #DSA', 0.0))[0]
        t_card = ctk.CTkFrame(self.left_learn_frame, fg_color=CARD_BG, corner_radius=8)
        t_card.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(t_card, text="Learned Title Guidelines", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(anchor="w", padx=10, pady=2)
        t_lbl = ctk.CTkLabel(t_card, text=title_inst, font=ctk.CTkFont(size=12, weight="bold"), wraplength=400, justify="left")
        t_lbl.pack(anchor="w", padx=10, pady=4)

        # Thumbnail preferences
        thumb_pref_str, thumb_conf = upload_prefs.get('thumbnail_preferences', ('[]', 0.0))
        try:
            thumb_prefs = json.loads(thumb_pref_str)
        except:
            thumb_prefs = []
            
        th_card = ctk.CTkFrame(self.left_learn_frame, fg_color=CARD_BG, corner_radius=8)
        th_card.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(th_card, text="CTR Thumbnail Preferences (Ranked)", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(anchor="w", padx=10, pady=2)
        if thumb_prefs:
            for idx, attr in enumerate(thumb_prefs):
                clean_attr = attr.replace('has_', 'With ').replace('_', ' ').title()
                ctk.CTkLabel(th_card, text=f"{idx+1}. {clean_attr}", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=20)
        else:
            ctk.CTkLabel(th_card, text="No thumbnail ranking history yet.", font=ctk.CTkFont(size=12, slant="italic")).pack(anchor="w", padx=10, pady=2)

        # --- RIGHT PANEL: Visual Sequences & Keywords ---
        # 1. Keywords weights
        cursor.execute("SELECT keyword, avg_score, sample_count FROM keyword_weights ORDER BY avg_score DESC LIMIT 10")
        kw_rows = cursor.fetchall()
        
        kw_title = ctk.CTkLabel(self.right_learn_frame, text="Top Keywords & Performance", font=ctk.CTkFont(size=14, weight="bold"))
        kw_title.pack(anchor="w", padx=10, pady=(10, 5))
        
        if kw_rows:
            for kw, avg_score, cnt in kw_rows:
                k_row = ctk.CTkFrame(self.right_learn_frame, fg_color=BG_DARK, corner_radius=6)
                k_row.pack(fill="x", padx=10, pady=2)
                ctk.CTkLabel(k_row, text=kw.title(), font=ctk.CTkFont(weight="bold"), width=200, anchor="w").pack(side="left", padx=10, pady=3)
                ctk.CTkLabel(k_row, text=f"Score: {avg_score:.1f}", font=ctk.CTkFont(size=12), text_color="#38bdf8", width=100, anchor="w").pack(side="left", padx=5)
                ctk.CTkLabel(k_row, text=f"Samples: {cnt}", font=ctk.CTkFont(size=10), text_color="gray").pack(side="right", padx=10)
        else:
            ctk.CTkLabel(self.right_learn_frame, text="No keyword weights data available yet.", font=ctk.CTkFont(size=12, slant="italic")).pack(anchor="w", padx=15, pady=5)
            
        # 2. Visual preferences
        cursor.execute("SELECT algorithm_category, best_visual_sequence, confidence, sample_count FROM visual_preferences")
        vis_rows = cursor.fetchall()
        
        vis_title = ctk.CTkLabel(self.right_learn_frame, text="Best Visual Sequences by Niche", font=ctk.CTkFont(size=14, weight="bold"))
        vis_title.pack(anchor="w", padx=10, pady=(20, 5))
        
        if vis_rows:
            for cat, seq_json, conf, cnt in vis_rows:
                try:
                    seq = json.loads(seq_json)
                except:
                    seq = []
                
                v_card = ctk.CTkFrame(self.right_learn_frame, fg_color=CARD_BG, corner_radius=8)
                v_card.pack(fill="x", padx=10, pady=5)
                ctk.CTkLabel(v_card, text=cat.upper(), font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(anchor="w", padx=10, pady=2)
                
                seq_str = " → ".join(seq)
                ctk.CTkLabel(v_card, text=seq_str, font=ctk.CTkFont(size=12, weight="bold"), wraplength=420, justify="left").pack(anchor="w", padx=10, pady=2)
                ctk.CTkLabel(v_card, text=f"Confidence: {conf:.2f} (Samples: {cnt})", font=ctk.CTkFont(size=9), text_color="#10b981" if conf > 0.4 else "gray").pack(anchor="w", padx=10, pady=2)
        else:
            ctk.CTkLabel(self.right_learn_frame, text="No visual sequences cached yet.", font=ctk.CTkFont(size=12, slant="italic")).pack(anchor="w", padx=15, pady=5)
            
        conn.close()

    def run_now_event(self):
        topic = self.topic_entry.get().strip()
        niche = self.niche_var.get()
        video_type = self.video_type_var.get()

        # Prepend [long] tag if long-form selected
        if topic and video_type == "long":
            topic = f"[long] {topic}"
        elif not topic and video_type == "long":
            # Auto-pick a topic and mark as long
            topic = None  # job() will auto-pick, but we'll pass video_type via niche later

        self.status_indicator.configure(text=f"● {'LONG-FORM' if video_type == 'long' else 'SHORT'} RUNNING",
                                        text_color="#7c3aed" if video_type == "long" else WARNING_COLOR)
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

    def run_intelligence_event(self):
        """Triggers the YouTube Intelligence Engine and shows a report."""
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
        from tkinter import messagebox
        if messagebox.askyesno("Gemini Quota Limits", f"{quota_info}\n\nOpen AI Studio dashboard?"):
            quota_manager.open_ai_studio_dashboard()

    def change_appearance_mode_event(self, mode: str):
        ctk.set_appearance_mode(mode)

if __name__ == "__main__":
    app = App()
    app.mainloop()
