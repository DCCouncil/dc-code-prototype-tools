import sys, time, os, lxml.etree as etree, re
from parse_bill import parse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, DirCreatedEvent
from pygments.lexers import XmlLexer
from pygments.formatters import HtmlFormatter
from pygments import highlight
from shutil import rmtree

def is_docx(path):
    base = os.path.basename(path)
    return path.endswith('.docx') and not base.startswith('~')

xml_lexer = XmlLexer()
html_formatter = HtmlFormatter(style='igor')

error_re = re.compile(r'errors="(\d+)"')

class EventHandler(FileSystemEventHandler):
    def __init__(self, in_path, out_path):
        self.in_path = in_path
        self.out_path = out_path

    def make_index(self, src_path):
        pyg_path = self.pygments_path(src_path)
        children = os.listdir(pyg_path)
        html = '<ul>'
        for child in children:
            if child == 'index.html':
                continue
            url_path = '#' + os.path.join(self.rel_path(src_path), child)
            child_path = os.path.join(pyg_path, child)
            glyph = '&#128194;'
            error = ''
            if not os.path.isdir(child_path):
                glyph = '&nbsp;'
                with open(os.path.join(self.raw_path(src_path), child)[:-4] + 'xml', 'r') as f:
                    match = error_re.search(f.readline())
                    if match:
                        error = ' <span class="error">({} errors)</span>'.format(match.group(1))
            html += '<li>{} <a href="{}">{}</a>{}</li>'.format(glyph, url_path, child, error)
        html += '</ul>'
        with open(os.path.join(pyg_path, 'index.html'), 'w') as f:
            f.write(html)

    def rel_path(self, src_path):
        return os.path.relpath(src_path, self.in_path)

    def raw_path(self, src_path):
        path = os.path.join(self.out_path, 'raw', self.rel_path(src_path))
        if is_docx(src_path):
            path = path[:-4] + 'xml'
        return path

    def pygments_path(self, src_path):
        path = os.path.join(self.out_path, 'pygments', self.rel_path(src_path))
        if is_docx(src_path):
            path = path[:-4] + 'html'
        return path

    def make_dir(self, src_path, update_index=True):
        try:
            os.makedirs(self.raw_path(src_path))
            os.makedirs(self.pygments_path(src_path))
        except OSError:
            pass
        if update_index:
            self.make_index(src_path)

    def make_file(self, src_path, update_index=True):
        try:
            dom = parse(src_path)
            xml = etree.tostring(dom, pretty_print=True, encoding="utf-8")
        except BaseException as e:
            print()
            xml = '<error errors="1">A fatal parsing error occurred. Please contact support. {}</error>'.format(e).encode('utf-8')
        with open(self.raw_path(src_path), 'wb') as f:
            f.write(xml)
        html = highlight(xml, xml_lexer, html_formatter)
        with open(self.pygments_path(src_path), 'w') as f:
            f.write(html)
        if update_index:
            self.make_index(os.path.dirname(src_path))

    def delete_dir(self, src_path):
        rmtree(self.raw_path(src_path))
        rmtree(self.pygments_path(src_path))
        self.make_index(os.path.dirname(src_path))

    def delete_file(self, src_path):
        os.remove(self.raw_path(src_path))
        os.remove(self.pygments_path(src_path))
        self.make_index(os.path.dirname(src_path))

    def on_created(self, event):
        if event.is_directory:
            self.make_dir(event.src_path)
        else:
            self.make_file(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        else:
            self.make_file(event.src_path)

    def on_deleted(self, event):
        if event.is_directory:
            self.delete_dir(event.src_path)
        else:
            self.delete_file(event.src_path)

    def on_moved(self, event):
        if event.is_directory or is_docx(event.src_path) and is_docx(event.dest_path):
            os.rename(self.raw_path(event.src_path), self.raw_path(event.dest_path))
            os.rename(self.raw_path(event.src_path), self.raw_path(event.dest_path))
        elif is_docx(event.src_path):
            self.delete_file(event.src_path)
        elif is_docx(event.dest_path):
            self.make_file(event.dest_path)

def walk(event_handler):
    dirs_to_update = []
    for root, dirs, files in os.walk(event_handler.in_path):
        event_handler.make_dir(root, False)
        dirty = False
        for f in files:
            src_path = os.path.join(root, f)
            if not is_docx(src_path):
                continue
            raw_path = event_handler.raw_path(src_path)
            pyg_path = event_handler.pygments_path(src_path)
            src_mod_time = os.path.getmtime(src_path)
            try:
                raw_mod_time = os.path.getmtime(raw_path)
                pyg_mod_time = os.path.getmtime(pyg_path)
            except FileNotFoundError:
                dirty = True
                event_handler.make_file(src_path, False)
            else:
                if src_mod_time >= raw_mod_time or src_mod_time >= pyg_mod_time:
                    dirty = True
                    event_handler.make_file(src_path, False)
        if dirty:
            dirs_to_update.append(root)


    for path in dirs_to_update:
        event_handler.make_index(path)

if __name__ == '__main__':
    observer = Observer()
    in_path = os.path.abspath(sys.argv[1])
    out_path = os.path.abspath(sys.argv[2])
    event_handler = EventHandler(in_path, out_path)

    while True:
        walk(event_handler)
        time.sleep(1)

    # walk(event_handler)
    # observer.schedule(event_handler, in_path, recursive=True)
    # observer.start()
    # try:
    #     while True:
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     observer.stop()
    # observer.join()
