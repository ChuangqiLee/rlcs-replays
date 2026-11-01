"""Read-only, conservative manuscript statistics (Python 3.6 standard library).

This is a source counter, not a TeX engine. Never execute TeX or a Makefile.
"""
import datetime
import os
import re
import subprocess

TITLES = {
    'abstract': ('摘要', 'Abstract'), 'intro': ('引言', 'Introduction'),
    'introduction': ('引言', 'Introduction'), 'data': ('数据', 'Data'),
    'dataset': ('数据集', 'Dataset'), 'methods': ('方法', 'Methods'),
    'method': ('方法', 'Method'), 'results': ('结果', 'Results'),
    'results_push': ('前压结果', 'Push-up results'), 'results_who': ('行为主体结果', 'Who pushes up'),
    'results_worth': ('前压价值结果', 'Push-up value'), 'discussion': ('讨论', 'Discussion'),
    'conclusion': ('结论', 'Conclusion'), 'appendix': ('附录', 'Appendix'),
    'related work': ('相关工作', 'Related work'),
}


def within(path, root):
    return os.path.commonpath([os.path.realpath(path), os.path.realpath(root)]) == os.path.realpath(root)


def local_git(root, *args):
    try:
        return subprocess.check_output(['git', '-C', root] + list(args), stderr=subprocess.PIPE,
                                       timeout=4).decode('utf-8', 'replace').strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def commit(root, path):
    return local_git(root, 'log', '-1', '--format=%H', '--', path)


def clean_comments(text):
    return re.sub(r'(?<!\\)%[^\n]*', '', text)


def words(text):
    text = clean_comments(text)
    text = re.sub(r'\\(?:label|ref|eqref|cite\w*|includegraphics|bibliography)\*?(?:\[[^\]]*\])?\{[^}]*\}', '', text)
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    text = re.sub(r'\\[A-Za-z@]+\*?(?:\[[^\]]*\])?', ' ', text)
    return len(re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*|[\u3400-\u9fff]", text))


def pdf_metadata(path, root):
    result = {'available': False, 'pages': None, 'compiled': None, 'modified': None,
              'commit': None, 'compile_time_source': None}
    if not within(path, os.path.join(root, 'paper')):
        return result
    try:
        with open(path, 'rb') as handle:
            if handle.read(5) != b'%PDF-':
                return result
        result.update(available=True, modified=datetime.datetime.fromtimestamp(
            os.path.getmtime(path), datetime.timezone.utc).isoformat(),
            commit=commit(root, os.path.relpath(path, root)))
        # Optional local utility: handles compressed page trees correctly. No regex guess.
        info = subprocess.check_output(['pdfinfo', '-isodates', path], stderr=subprocess.PIPE,
                                       timeout=5).decode('utf-8', 'replace')
        fields = dict(line.split(':', 1) for line in info.splitlines() if ':' in line)
        count = fields.get('Pages', '').strip()
        result['pages'] = int(count) if count.isdigit() else None
        created = fields.get('CreationDate', '').strip()
        if re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:?\d\d)', created):
            result['compiled'] = created
            result['compile_time_source'] = 'PDF CreationDate'
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return result


def scan(root):
    base = os.path.join(root, 'paper')
    main = os.path.join(base, 'main.tex')
    sections, figures, modified = [], [], []
    missing = []

    def section(path, title, content, exists=True):
        key = os.path.splitext(os.path.basename(path))[0]
        pair = TITLES.get(title.lower()) or TITLES.get(key)
        clean = clean_comments(content)
        count = words(clean) if exists else None
        marker = re.search(r'^\s*%\s*dashboard-status:\s*(done|review|draft|not_started)\s*$', content, re.M)
        status = marker.group(1) if marker else ('draft' if count else 'not_started') if exists else 'unknown'
        if re.search(r'\\todo\b|\b(?:TODO|FIXME|TBD)\b', clean):
            status = 'draft'  # A contradictory "done" marker never hides placeholders.
        figs = len(re.findall(r'\\begin\{figure\*?\}', clean)) if exists else None
        rel = os.path.relpath(path, root)
        item = {'id': str(len(sections) + 1), 'path': rel,
                'name_zh': pair[0] if pair else '未知',
                'name_en': pair[1] if pair else (title if not re.search(r'[\u3000-\u9fff]', title) else 'Unknown'),
                'status': status, 'words': count, 'figure_count': figs,
                'commit': commit(root, rel) if exists else None,
                'progress': 100 if status == 'done' else 0 if status == 'not_started' else None}
        sections.append(item)
        for target in re.findall(r'\\includegraphics\*?(?:\[[^\]]*\])?\{([^}]+)\}', clean):
            figures.append({'id': str(len(figures) + 1), 'path': target,
                            'title_zh': '插图引用', 'title_en': 'Figure reference', 'status': 'unknown'})

    source_paths = []

    def expand(path, stack=()):
        index = len(source_paths)
        source_paths.append(path)
        real = os.path.realpath(path)
        if len(stack) > 32 or real in stack or not within(path, base):
            missing.append(os.path.relpath(path, root))
            return '\\dashboardmissing{' + str(index) + '}'
        try:
            with open(path, encoding='utf-8') as handle:
                text = handle.read()
            modified.append(os.path.getmtime(path))
        except (OSError, UnicodeError):
            missing.append(os.path.relpath(path, root))
            return '\\dashboardmissing{' + str(index) + '}'
        text = re.sub(r'(?<!\\)%(?!\s*dashboard-status:)[^\n]*', '', text)
        if path == main:
            text = text.split(r'\begin{document}', 1)[-1].split(r'\end{document}', 1)[0]
        marker = '\\dashboardfile{' + str(index) + '}'

        def include(match):
            name = match.group(1)
            name = name if name.endswith('.tex') else name + '.tex'
            candidate = os.path.join(base, name)
            if not os.path.isfile(candidate):
                candidate = os.path.join(os.path.dirname(path), name)
            return expand(candidate, stack + (real,)) + marker

        return marker + re.sub(r'\\(?:input|include)\{([^}]+)\}', include, text)

    if os.path.isfile(main) and within(main, base):
        text = expand(main)
        # File markers preserve source provenance without counting marker text.
        tokens = re.compile(r'\\dashboardfile\{(\d+)\}|\\dashboardmissing\{(\d+)\}|'
                            r'\\(?:section|chapter)\*?(?:\[[^\]]*\])?\{([^}]+)\}|'
                            r'\\begin\{abstract\}|\\end\{abstract\}')
        current_path, current_title, chunks, source_path, end = None, None, [], main, 0

        def finish():
            if current_path is not None:
                section(current_path, current_title, ''.join(chunks))

        for match in tokens.finditer(text):
            if current_path is not None:
                chunks.append(text[end:match.start()])
            if match.group(1) is not None:
                source_path = source_paths[int(match.group(1))]
            elif match.group(2) is not None:
                finish()
                path = source_paths[int(match.group(2))]
                section(path, os.path.splitext(os.path.basename(path))[0], '', False)
                current_path, current_title, chunks = None, None, []
            elif match.group(0) == r'\end{abstract}':
                finish()
                current_path, current_title, chunks = None, None, []
            else:
                finish()
                current_path = source_path
                current_title = match.group(3) or 'abstract'
                chunks = []
            end = match.end()
        if current_path is not None:
            chunks.append(text[end:])
            finish()
        elif not sections:
            # A document with prose but no section headings is still a draft.
            clean = re.sub(r'\\dashboardfile\{\d+\}', '', text)
            section(main, 'main', clean)
    complete = sum(s['status'] == 'done' for s in sections)
    all_known = bool(sections) and not missing
    return {'sections': sections, 'figures': figures, 'missing_files': missing,
            'words': sum(s['words'] or 0 for s in sections) if sections else None,
            'figure_count': sum(s['figure_count'] or 0 for s in sections) if sections else None,
            'counts_partial': bool(missing), 'completed_sections': complete if sections else None,
            'progress': 100.0 * complete / len(sections) if all_known else None,
            'commit': commit(root, 'paper'),
            'updated': datetime.datetime.fromtimestamp(max(modified), datetime.timezone.utc).isoformat() if modified else None,
            'pdf': pdf_metadata(os.path.join(base, 'main.pdf'), root)}
