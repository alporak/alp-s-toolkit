# ALPS Toolkit

Utilities for Teltonika workflows (GPS server, log parsing, Jira tracking, release tooling, and integrations).

## Important: Windows clone case-collision

If cloning fails on Windows with a case-collision warning for README, keep only one canonical file name in history (`README.md`).

## Patch notes (easy_catcher + jira_tracker)

The following patch captures the currently staged fixes in:

- `third_party/easy-catcher/easy_catcher.py`
- `third_party/jira-time-tracker/streamlit_app.py`

These changes mainly:

- make file paths absolute and script-location-based (more reliable when launched from other working directories),
- improve `process_folder` return value semantics in Easy Catcher,
- persist Jira auto-refresh settings to config,
- preload Jira worklogs and assigned tickets in parallel,
- preload teammate caches in parallel.

### easy_catcher patch

```diff
diff --git a/easy_catcher.py b/easy_catcher.py
index ebc5768..cc93984 100644
--- a/easy_catcher.py
+++ b/easy_catcher.py
@@ -14,11 +14,13 @@ from releasebook import Releasebook
 __version__ = '1.0.7'
 __author__ = "yuri.maksimenko@teltonika.lt"
 
-CATCHER_PATH = './catcher_mod/Catcher.exe'
-CLG2TXT_PATH = './catcher_mod/Clg2Txt.exe'
-CATCHER_LOG_TO_HEX_AND_ASCII_PATH = './catcherLogFileToHexAndAscii/catcherLogToAscii.exe'
-CONFIG_FILENAME = './config.yml'
-TEMP_FILENAME = './tempfile.tmp'
+_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
+
+CATCHER_PATH = os.path.join(_MODULE_DIR, 'catcher_mod', 'Catcher.exe')
+CLG2TXT_PATH = os.path.join(_MODULE_DIR, 'catcher_mod', 'Clg2Txt.exe')
+CATCHER_LOG_TO_HEX_AND_ASCII_PATH = os.path.join(_MODULE_DIR, 'catcherLogFileToHexAndAscii', 'catcherLogToAscii.exe')
+CONFIG_FILENAME = os.path.join(_MODULE_DIR, 'config.yml')
+TEMP_FILENAME = os.path.join(_MODULE_DIR, 'tempfile.tmp')
@@ -157,7 +159,7 @@ def get_db_filename(db_path):
 
 def search_spec_id_in_base(spec_id):
     result = None    
-    specids_filename = './specids.json'
+    specids_filename = os.path.join(_MODULE_DIR, 'specids.json')
     if spec_id == '1':
         return 'Base'
     try:
@@ -177,11 +179,16 @@ def search_spec_id_in_base(spec_id):
     
     
 def process_folder(logs_dir, config):
-    ret_val = False
+    """Process dump files in logs_dir.
+
+    Returns:
+        The path to the generated .log file on success, or None on failure.
+    """
+    output_log = None
     dump_files = glob.glob(os.path.join(logs_dir, "*.dmp"))
     if not dump_files:
         print('No dump files found...')
-        return ret_val
+        return output_log
 
     file_dates = extract_dates_from_logs(dump_files)
     if 'sort_logs' in config['general'] and config['general']['sort_logs']:
@@ -220,10 +227,10 @@ def process_folder(logs_dir, config):
                 print(f'Hex and ASCII log created: {txt_path}')
                 run_catcher(CATCHER_PATH, merged_files[0])
                 print('Completed.')
-                ret_val = True
+                output_log = txt_path
     if os.path.isfile(TEMP_FILENAME):
         os.unlink(TEMP_FILENAME)
-    return ret_val
+    return output_log
```

### jira_tracker patch

```diff
diff --git a/streamlit_app.py b/streamlit_app.py
index 22c451d..007f7a0 100644
--- a/streamlit_app.py
+++ b/streamlit_app.py
@@ -11,8 +11,9 @@ import concurrent.futures
 from streamlit_autorefresh import st_autorefresh
 
 DOMAIN = "teltonika-telematics.atlassian.net"
-CONFIG_FILE = "jira_config.json"
-CACHE_FILE = "worklog_cache.json"
+_APP_DIR = os.path.dirname(os.path.abspath(__file__))
+CONFIG_FILE = os.path.join(_APP_DIR, "jira_config.json")
+CACHE_FILE = os.path.join(_APP_DIR, "worklog_cache.json")
 DEFAULT_REFRESH_INTERVAL = 300  # 5 minutes
 MAX_WORKERS = 20
 LOOKBACK_DAYS = 14
@@ -168,6 +169,7 @@ def save_disk_cache(user_cache, cache_time):
 def clear_cache():
     st.session_state.user_cache = {}
     st.session_state.cache_time = 0
+    st.session_state.assigned_tickets = None
     save_disk_cache({}, 0)
 
 
@@ -588,25 +590,27 @@ def filter_tickets_for_edit(tickets, view_mode, selected_date=None):
 # ═════════════════════════════════════════════════════════════════════════
 
 def main():
+    # ── Session state defaults ────────────────────────────────────────
+    if "config" not in st.session_state:
+        st.session_state.config = load_config()
+        if "teammates" not in st.session_state.config:
+            st.session_state.config["teammates"] = []
+
     # ── Session state defaults ────────────────────────────────────────
     defaults = {
         "selected_user_email": "",
         "view_mode": "today",
         "selected_date": None,
-        "refresh_enabled": True,
-        "refresh_interval": DEFAULT_REFRESH_INTERVAL,
+        "refresh_enabled": st.session_state.config.get("refresh_enabled", True),
+        "refresh_interval": st.session_state.config.get("refresh_interval", DEFAULT_REFRESH_INTERVAL),
         "cache_time": 0,
         "edit_mode": False,
+        "assigned_tickets": None,
     }
     for k, v in defaults.items():
         if k not in st.session_state:
             st.session_state[k] = v
 
-    if "config" not in st.session_state:
-        st.session_state.config = load_config()
-        if "teammates" not in st.session_state.config:
-            st.session_state.config["teammates"] = []
-
     if "user_cache" not in st.session_state:
         cached, ct = load_disk_cache()
         st.session_state.user_cache = cached
@@ -632,16 +636,27 @@ def main():
         ref_en = st.checkbox("Enable Auto-Refresh", value=st.session_state.refresh_enabled, key="cb_ref")
         if ref_en != st.session_state.refresh_enabled:
             st.session_state.refresh_enabled = ref_en
+            st.session_state.config["refresh_enabled"] = ref_en
+            save_config(st.session_state.config)
 
         opts = [60, 120, 300, 600, 900]
+        # Ensure current interval is in opts, otherwise default to 300
+        current_interval = st.session_state.refresh_interval
+        if current_interval not in opts:
+            current_interval = 300
+
         ref_iv = st.selectbox(
             "Refresh Interval", options=opts,
             format_func=lambda x: f"{x // 60} min",
-            index=opts.index(st.session_state.refresh_interval) if st.session_state.refresh_interval in opts else 2,
+            index=opts.index(current_interval),
             key="sb_iv",
         )
         if ref_iv != st.session_state.refresh_interval:
             st.session_state.refresh_interval = ref_iv
+            st.session_state.config["refresh_interval"] = ref_iv
+            save_config(st.session_state.config)
+            clear_cache()  # Clear cache so new interval applies immediately
+            st.rerun()
 
         st.divider()
         st.subheader("Jira Credentials")
@@ -739,19 +754,31 @@ def main():
             clear_cache()
             st.rerun()
 
-    # ── Ensure ME is loaded first ─────────────────────────────────────
+    # ── Load ME worklogs + assigned tickets in parallel ───────────────
     me_cache_key = my_email
-    if me_cache_key not in st.session_state.user_cache:
+    me_missing = me_cache_key not in st.session_state.user_cache
+    assigned_missing = st.session_state.assigned_tickets is None
+
+    if me_missing or assigned_missing:
         with st.spinner(random.choice(LOADING_MESSAGES)):
-            tickets, display_name, error = fetch_user_worklogs(my_email, my_token, "")
-        if error:
-            st.error(f"❌ Error: {error}")
-            st.session_state.user_cache[me_cache_key] = {"tickets": [], "display_name": "ME"}
-        else:
-            st.session_state.user_cache[me_cache_key] = {"tickets": tickets, "display_name": display_name}
-        if st.session_state.cache_time == 0:
-            st.session_state.cache_time = time.time()
-        save_disk_cache(st.session_state.user_cache, st.session_state.cache_time)
+            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
+                fut_me = pool.submit(fetch_user_worklogs, my_email, my_token, "") if me_missing else None
+                fut_assigned = pool.submit(fetch_assigned_tickets, my_email, my_token) if assigned_missing else None
+
+                if fut_me:
+                    tickets, display_name, error = fut_me.result()
+                    if error:
+                        st.error(f"❌ Error: {error}")
+                        st.session_state.user_cache[me_cache_key] = {"tickets": [], "display_name": "ME"}
+                    else:
+                        st.session_state.user_cache[me_cache_key] = {"tickets": tickets, "display_name": display_name}
+                    if st.session_state.cache_time == 0:
+                        st.session_state.cache_time = time.time()
+                    save_disk_cache(st.session_state.user_cache, st.session_state.cache_time)
+
+                if fut_assigned:
+                    assigned, err = fut_assigned.result()
+                    st.session_state.assigned_tickets = assigned if not err else []

     # ── Team buttons ──────────────────────────────────────────────────
     teammates = st.session_state.config["teammates"]
```

### jira_tracker additional hunks

```diff
@@ -966,78 +993,72 @@ def main():
      # ── Log Work section (ME only) ─────────────────────────────────────
      if is_viewing_me:
           with st.expander("📝 Log Work", expanded=False):
-            # Load assigned tickets on demand
-            if "assigned_tickets" not in st.session_state:
-                st.session_state.assigned_tickets = None
-
-            if st.session_state.assigned_tickets is None:
-                with st.spinner("Loading assigned tickets..."):
-                    assigned, err = fetch_assigned_tickets(my_email, my_token)
-                if err:
-                    st.error(f"Could not load tickets: {err}")
-                else:
-                    st.session_state.assigned_tickets = assigned
-                    st.rerun()
+            assigned = st.session_state.assigned_tickets or []
+            if not assigned:
+                st.info("No assigned tickets found.")
                else:
-                assigned = st.session_state.assigned_tickets
-                if not assigned:
-                    st.info("No assigned tickets found.")
-                else:
-                    # Ticket selector
-                    ticket_options = [f"{t['key']}  {'🔵' if t['status'].lower() in ('in progress','in development','in review') else '⚪'}  {t['summary'][:60]}" for t in assigned]
-                    selected_idx = st.selectbox(
-                        "Ticket", range(len(ticket_options)),
-                        format_func=lambda i: ticket_options[i],
-                        key="log_ticket_sel",
-                        label_visibility="collapsed",
-                    )
-                    lc1, lc2 = st.columns([1, 3])
-                    with lc1:
-                        log_time = st.text_input("Time", placeholder="1h 30m", key="log_time_input", label_visibility="collapsed")
-                    with lc2:
-                        log_desc = st.text_input("Description", placeholder="What did you work on?", key="log_desc_input", label_visibility="collapsed")
-
-                    lc3, lc4 = st.columns([1, 1])
-                    with lc3:
-                        if st.button("📝 Log Work", use_container_width=True, key="log_submit_btn"):
-                            parsed = parse_time_input(log_time)
-                            if parsed is None or parsed <= 0:
-                                st.error("⚠️ Enter a valid time (e.g. 1h 30m, 2h, 45m)")
-                            else:
-                                ticket_key = assigned[selected_idx]["key"]
-                                ok, msg = add_worklog(my_email, my_token, ticket_key, parsed, log_desc)
-                                if ok:
-                                    st.success(f"✅ Logged {seconds_to_display(parsed)} to {ticket_key}")
-                                    clear_cache()
-                                    st.session_state.assigned_tickets = None
-                                    time.sleep(0.5)
-                                    st.rerun()
-                                else:
-                                    st.error(f"❌ Failed: {msg}")
-                    with lc4:
-                        if st.button("🔄 Refresh tickets", use_container_width=True, key="log_refresh_btn"):
-                            st.session_state.assigned_tickets = None
-                            st.rerun()
+                # Ticket selector
+                ticket_options = [f"{t['key']}  {'🔵' if t['status'].lower() in ('in progress','in development','in review') else '⚪'}  {t['summary'][:60]}" for t in assigned]
+                selected_idx = st.selectbox(
+                    "Ticket", range(len(ticket_options)),
+                    format_func=lambda i: ticket_options[i],
+                    key="log_ticket_sel",
+                    label_visibility="collapsed",
+                )
+                lc1, lc2 = st.columns([1, 3])
+                with lc1:
+                    log_time = st.text_input("Time", placeholder="1h 30m", key="log_time_input", label_visibility="collapsed")
+                with lc2:
+                    log_desc = st.text_input("Description", placeholder="What did you work on?", key="log_desc_input", label_visibility="collapsed")
+
+                lc3, lc4 = st.columns([1, 1])
+                with lc3:
+                    if st.button("📝 Log Work", use_container_width=True, key="log_submit_btn"):
+                        parsed = parse_time_input(log_time)
+                        if parsed is None or parsed <= 0:
+                            st.error("⚠️ Enter a valid time (e.g. 1h 30m, 2h, 45m)")
+                        else:
+                            ticket_key = assigned[selected_idx]["key"]
+                            ok, msg = add_worklog(my_email, my_token, ticket_key, parsed, log_desc)
+                            if ok:
+                                st.success(f"✅ Logged {seconds_to_display(parsed)} to {ticket_key}")
+                                clear_cache()
+                                time.sleep(0.5)
+                                st.rerun()
+                            else:
+                                st.error(f"❌ Failed: {msg}")
+                with lc4:
+                    if st.button("🔄 Refresh tickets", use_container_width=True, key="log_refresh_btn"):
+                        st.session_state.assigned_tickets = None
+                        st.rerun()
@@
 def _background_load_teammates(my_email, my_token):
-    """Fetch the next uncached teammate, then rerun. Called after display is rendered."""
+    """Fetch all uncached teammates in parallel, then rerun once."""
      uncached = [
           tm for tm in st.session_state.config.get("teammates", [])
           if tm["email"] not in st.session_state.user_cache
      ]
-    if uncached:
-        tm = uncached[0]
+    if not uncached:
+        return
+
+    def _load_one(tm):
           tickets, display_name, error = fetch_user_worklogs(my_email, my_token, tm["email"])
           if error:
-            st.session_state.user_cache[tm["email"]] = {"tickets": [], "display_name": tm["email"]}
-        else:
-            st.session_state.user_cache[tm["email"]] = {"tickets": tickets, "display_name": display_name}
-        save_disk_cache(st.session_state.user_cache, st.session_state.cache_time)
-        st.rerun()
+            return tm["email"], {"tickets": [], "display_name": tm["email"]}
+        return tm["email"], {"tickets": tickets, "display_name": display_name}
+
+    with concurrent.futures.ThreadPoolExecutor(max_workers=len(uncached)) as pool:
+        futures = [pool.submit(_load_one, tm) for tm in uncached]
+        for fut in concurrent.futures.as_completed(futures):
+            email, data = fut.result()
+            st.session_state.user_cache[email] = data
+
+    save_disk_cache(st.session_state.user_cache, st.session_state.cache_time)
+    st.rerun()
```

## Applying the patch blocks

1. Save each diff block into its own file (for example, `easy-catcher.patch` and `jira-time-tracker.patch`).
2. Apply from each submodule root:

```bash
git -C third_party/easy-catcher apply easy-catcher.patch
git -C third_party/jira-time-tracker apply jira-time-tracker.patch
```

3. Verify:

```bash
git -C third_party/easy-catcher diff -- easy_catcher.py
git -C third_party/jira-time-tracker diff -- streamlit_app.py
```
