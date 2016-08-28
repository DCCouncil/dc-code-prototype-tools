import sys, time, os, lxml.etree as etree, re
from parse_law import parse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, DirCreatedEvent
from shutil import rmtree

def is_docx(path):
    base = os.path.basename(path)
    return path.endswith('.docx') and not base.startswith('~')

error_re = re.compile(r'errors="(\d+)"')

class EventHandler(FileSystemEventHandler):
    def __init__(self, in_path, out_path):
        self.in_path = in_path
        self.out_path = out_path

    def rel_path(self, src_path):
        return os.path.relpath(src_path, self.in_path)

    def raw_path(self, src_path):
        path = os.path.join(self.out_path, 'raw', self.rel_path(src_path))
        if is_docx(src_path):
            path = path[:-4] + 'xml'
        return path

    def make_dir(self, src_path):
        try:
            os.makedirs(self.raw_path(src_path))
        except OSError:
            pass

    def make_file(self, src_path):
        try:
            dom = parse(src_path)
            xml = etree.tostring(dom, pretty_print=True, encoding="utf-8")
        except BaseException as e:
            print()
            xml = '<error errors="1">A fatal parsing error occurred. Please contact support. {}</error>'.format(e).encode('utf-8')
        with open(self.raw_path(src_path), 'wb') as f:
            f.write(xml)

    def delete_dir(self, src_path):
        rmtree(self.raw_path(src_path))
        self.make_index(os.path.dirname(src_path))

    def delete_file(self, src_path):
        os.remove(self.raw_path(src_path))
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
        event_handler.make_dir(root)
        for f in files:
            src_path = os.path.join(root, f)
            if not is_docx(src_path):
                continue
            raw_path = event_handler.raw_path(src_path)
            src_mod_time = os.path.getmtime(src_path)
            try:
                raw_mod_time = os.path.getmtime(raw_path)
            except FileNotFoundError:
                event_handler.make_file(src_path)
            else:
                if src_mod_time >= raw_mod_time :
                    dirty = True
                    event_handler.make_file(src_path)

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
