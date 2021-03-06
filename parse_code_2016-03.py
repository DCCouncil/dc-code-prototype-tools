import os, os.path, sys, json, time, re
import lxml.etree as etree
from parsers import Parser, _make_node, _para_text_content, _para_rich_text_content
from worddoc import open_docx
import matchers
import copy

div_re = re.compile(r'(?P<div>\w+)\.docx$')

def parse_file(dom, path_to_file, start_para_index):
	# Open the Word file. Use a cached json file if it exists
	# since that's faster that opening the raw .docx file.
	print('\nparsing {}'.format(path_to_file), file=sys.stderr)
	fhash = _hashfile(path_to_file)
	doc = None
	tmp_doc = "/tmp/doc.cache.{}.json".format(fhash)
	if os.path.exists(tmp_doc):
		doc = json.load(open(tmp_doc))
		print('loading from', tmp_doc, file=sys.stderr)
	else:
		print('saving to', tmp_doc, file=sys.stderr)

	if doc is None:
		doc = open_docx(path_to_file, pict=pict_handler)
		for section in doc['sections']:
			for para_index, para in enumerate(section["paragraphs"], start_para_index):
				para['index'] = para_index
			start_para_index += len(section['paragraphs'])
		with open(tmp_doc, "w") as doccache:
			json.dump( doc, doccache, indent=2)
	try:
		# Parse each section.
		for section in doc["sections"]:
			parse_doc_section(section, dom)
	except:
		import traceback
		traceback.print_exc()
	return start_para_index

def main():
	# Form the output DOM.
	dom = etree.Element("code")
	_make_node(dom, "heading", "Code of the District of Columbia")
	meta = _make_node(dom, "meta", None)
	recency = etree.fromstring(sys.argv[2] if len(sys.argv) > 2 else """
    <recency>
      <law>
        <law>21-46</law>
        <effective>2016-01-09</effective>
      </law>
      <emergency>
        <law>21-240</law>
        <effective>2015-12-21</effective>
      </emergency>
      <federal>
        <law>114-95</law>
        <effective>2015-12-10</effective>
      </federal>
    </recency>
""")
	meta.append(recency)
	start_time = time.time()
	DIR = sys.argv[1]
	try:
		all_file_names = os.listdir(DIR)
	except NotADirectoryError:
		file_paths = [DIR]
	else:
		file_paths = [os.path.join(DIR, fn) for fn in all_file_names if fn.endswith('.docx')]
	start_para_index = 0
	for fp in file_paths:
		start_para_index = parse_file(dom, fp, start_para_index)

	# print(time.time() - start_time)
	# Output, being careful we get UTF-8 to the byte stream.
	sys.stdout.buffer.write(etree.tostring(dom, pretty_print=True, encoding="utf-8", xml_declaration=True))

def pict_handler(node):
	return "@@PICT@@"

def _hashfile(filepath):
    import hashlib
    sha1 = hashlib.sha1()
    f = open(filepath, 'rb')
    try:
        sha1.update(f.read())
    finally:
        f.close()
    return sha1.hexdigest()


def parse_doc_section(section, dom):
	def prep_para(para):
		para['text'] = _para_text_content(para)
		para['richtext'] = _para_rich_text_content(para)
		def next_para():
			paras = section['paragraphs']
			next_index = para['index'] - paras[0]['index'] + 1
			if next_index >= len(paras):
				return None
			next_p = prep_para(copy.deepcopy(paras[next_index]))
			if matchers.empty(next_p):
				next_p = next_p['next']()
			return next_p
		para['next'] = next_para;
		return para

	parser = Parser(dom)

	unhandled_count = 0
	handled_count = 0
	for para in section["paragraphs"]:
		prep_para(para)
		if not para['text']:
			continue
		success = parser(para)
		if not success and para['text']:
			unhandled_count += 1
			print('unhandled para {}:'.format(para['index']), para, '\n', file=sys.stderr)
		elif success:
			handled_count += 1
	print('handled paras: {}'.format(handled_count), file=sys.stderr)
	print('unhandled paras: {}'.format(unhandled_count), file=sys.stderr)


if __name__ == '__main__':
	main()
