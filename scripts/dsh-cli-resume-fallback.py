import io
import sys
from pathlib import Path

REPO = Path(r'D:\GitHub\codex-mobile-bridge')
SERVICE = REPO / 'bridge' / 'app' / 'service.py'
HTTPD = REPO / 'bridge' / 'api' / 'httpd.py'

METHOD_ANCHOR = "    def _dispatch(self, session, key, entry):\n"
METHOD = '''    def send_via_cli_resume(self, thread_id, text, submission_id, mode="send", files=None):
        """Fallback writer: submit the turn through `codex exec resume`.

        Codex 0.171 replaced the desktop named pipe with an app-server control
        socket that this bridge cannot attach to yet. The CLI can still resume
        the same thread and append the turn to the same session store, which the
        gateway already reads, so sending keeps working without the IPC.
        """
        row = {}
        try:
            row = self.store.get(thread_id) or {}
        except Exception:
            row = {}
        cwd = row.get('cwd') or os.path.expanduser('~')
        if not os.path.isdir(cwd):
            cwd = os.path.expanduser('~')
        executable = getattr(getattr(self, 'catalog_reader', None), 'executable', None) or 'codex'
        prompt = text or ''
        if files:
            paths = [f.get('path') for f in files if isinstance(f, dict) and f.get('path')]
            if paths:
                prompt = prompt + "\\n\\n" + "\\n".join("- " + str(p) for p in paths)
        command = [str(executable), 'exec', '--skip-git-repo-check', '--json', 'resume', str(thread_id), prompt]
        if os.name == 'nt' and str(executable).lower().endswith(('.cmd', '.bat')):
            command = [os.environ.get('COMSPEC', 'cmd.exe'), '/c'] + command
        creation = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
        environment = dict(os.environ)
        environment.setdefault('CODEX_HOME', str(self.codex_home))
        log_path = os.path.join(str(self.data_dir), 'cli-resume.log')
        log = open(log_path, 'ab')
        try:
            process = subprocess.Popen(
                command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, close_fds=True, creationflags=creation)
        except OSError as exc:
            log.close()
            raise IPCError('CLI 兜底发送启动失败：%s' % exc) from exc
        self.submissions[str(thread_id) + ':' + str(submission_id)] = {
            'text': text, 'mode': mode, 'status': 'accepted',
            'at': time.time(), 'cliResumePid': process.pid}
        try:
            self._save_ledger()
        except Exception:
            pass
        LOG.info('CLI resume fallback submitted thread=%s pid=%s', thread_id, process.pid)
        return {'status': 'accepted', 'id': submission_id, 'cliResume': True}

'''

HTTPD_OLD = '''            elif action == "send":
                result = bridge.send(thread_id, body.get("text"), body.get("id", ""), body.get("mode", "send"),
                                     body.get("skills", []), work_mode=body.get("workMode"),
                                     attachments=body.get('attachments'), references=body.get('references'), ui_locale=body.get("uiLocale"))
'''

HTTPD_NEW = '''            elif action == "send":
                try:
                    result = bridge.send(thread_id, body.get("text"), body.get("id", ""), body.get("mode", "send"),
                                         body.get("skills", []), work_mode=body.get("workMode"),
                                         attachments=body.get('attachments'), references=body.get('references'), ui_locale=body.get("uiLocale"))
                except (IPCError, StoreUnavailable) as exc:
                    LOG.warning("desktop IPC unavailable (%s); falling back to CLI resume", exc)
                    result = bridge.send_via_cli_resume(
                        thread_id, body.get("text"), body.get("id", ""), body.get("mode", "send"),
                        bridge.uploads.resolve(thread_id, body.get('attachments') or []))
'''


def patch(path, old, new, marker=None):
    data = path.read_text(encoding='utf-8')
    if marker and marker in data:
        print('already patched:', path.name)
        return False
    if old not in data:
        raise SystemExit('anchor not found in %s' % path)
    path.write_text(data.replace(old, new, 1), encoding='utf-8')
    print('patched:', path.name)
    return True


def main():
    patch(SERVICE, METHOD_ANCHOR, METHOD + METHOD_ANCHOR, marker='def send_via_cli_resume')
    patch(HTTPD, HTTPD_OLD, HTTPD_NEW, marker='falling back to CLI resume')


if __name__ == '__main__':
    main()
