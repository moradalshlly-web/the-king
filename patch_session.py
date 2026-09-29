path = "brain/session.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# Only create a workspace session if a checkpoint was created (real changes)
old = """        # 2. Create isolated workspace session
        try:
            sid = self.workspace.create_session(
                conversation_ref=conversation_ref,
                note=note or "Auto session snapshot at close",
            )
            summary["session_id"] = sid
        except Exception as e:
            summary["status"] = f"workspace_error: {e}\""""

new = """        # 2. Create isolated workspace session ONLY if there were real changes
        if summary.get("checkpoint_hash"):
            try:
                sid = self.workspace.create_session(
                    conversation_ref=conversation_ref,
                    note=note or "Auto session snapshot at close",
                )
                summary["session_id"] = sid
            except Exception as e:
                summary["status"] = f"workspace_error: {e}"
        else:
            summary["session_id"] = None"""

if old not in c:
    print("NOT FOUND")
else:
    c = c.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("PATCHED")
