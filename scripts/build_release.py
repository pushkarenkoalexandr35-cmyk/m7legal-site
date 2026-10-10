#!/usr/bin/env python3
"""Reproducible M7Legal release build. Never modifies the production directory.

Examples:
 python3 scripts/build_release.py --source . --output /tmp/m7-production --mode production
 python3 scripts/build_release.py --source . --output /tmp/m7-staging --mode staging --prefix /m7legal-preview-20261009/

Source stays conservative (robots disallow/noindex); this build explicitly converts it.
Staging mode always prevents lead delivery and indexing.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT_MARKER = "m7legal.ru"
PREVIEW_JS = r"""(()=>{
 const p=document.documentElement.dataset.previewPrefix || '/m7legal-preview-20261009/';
 document.querySelectorAll('a[href]').forEach(a=>{
   const h=a.getAttribute('href')||'';
   if(h.startsWith('/')&&!h.startsWith('//')&&!h.startsWith(p)) a.setAttribute('href',p+h.slice(1));
 });
 document.querySelectorAll('form').forEach(form=>{
   form.setAttribute('action','#');
   form.addEventListener('submit',e=>{
     e.preventDefault();e.stopImmediatePropagation();
     const el=form.querySelector('#m7lead-status,[data-form-status]');
     if(el)el.textContent='Предпросмотр: заявка не отправлена';
   },true);
 });
 document.body.insertAdjacentHTML('afterbegin',
 '<div role="status" class="m7-preview-banner" style="position:relative;z-index:60;background:#f5c9ab;color:#222;padding:10px 20px;text-align:center;font:600 13px Arial,sans-serif">ПРЕДПРОСМОТР M7LEGAL — заявки отключены; действующий сайт не изменён</div>');
})();"""

def package(source: Path, output: Path, mode: str, prefix: str) -> dict:
    if source.resolve() == output.resolve() or source.resolve() in output.resolve().parents:
        raise ValueError("Output must not be inside the source directory")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be absent or empty (protect against overwriting live data)")
    output.mkdir(parents=True, exist_ok=True)
    report = {'mode': mode, 'pages': 0, 'assets': 0, 'broken_local_links': [],
              'invalid_local_anchors': [], 'noindex_release_pages': [],
              'form_script_on_staging': [], 'missing_analytics_script': []}
    files = []
    for path in source.rglob('*'):
        if not path.is_file() or '.git' in path.parts or 'scripts' in path.parts:
            continue
        rel = path.relative_to(source)
        # Only copy publishable assets. Omit documentation and source-only configurations.
        if path.suffix.lower() not in ('.html','.css','.js','.svg','.png','.jpg','.jpeg','.webp','.ico','.txt','.xml','.woff','.woff2'):
            continue
        if path.suffix.lower() == '.txt' and path.name not in (
            'robots.txt','robots.production.txt','7f8c0e1a9d4b6c2f5e3a1b7d9c4e6f20.txt'):
            continue
        if path.name in ('robots.production.txt','sitemap.production.xml','robots.txt','preview.js'):
            continue
        if path.suffix.lower() == '.xml' and path.name != 'BingSiteAuth.xml':
            continue
        files.append((path, rel))

    # Nginx caches static CSS/JS for 30 days. Every release must reference
    # content-addressed URLs to avoid mixing old CSS with new HTML.
    asset_versions = {}
    for asset in ("styles.css", "site-pages.css", "legacy.css", "site.js", "m7-form.js", "legacy-home.css"):
        resource = source / ("assets/legacy-home.css" if asset == "legacy-home.css" else asset)
        if resource.is_file():
            asset_versions[asset] = hashlib.sha256(resource.read_bytes()).hexdigest()[:12]

    def version_local_asset(match):
        start, quote, value = match.groups()
        if value.startswith(("https://", "http://", "//", "data:")):
            return match.group(0)
        url, hash_mark, fragment = value.partition("#")
        pathname, query_mark, query = url.partition("?")
        name = pathname.rsplit("/", 1)[-1]
        if name not in asset_versions:
            return match.group(0)
        retained = [v for v in query.split("&") if v and not v.startswith("v=")]
        retained.append("v=" + asset_versions[name])
        return start + quote + pathname + "?" + "&".join(retained) + (hash_mark + fragment if hash_mark else "") + quote

    for path, rel in files:
        dest = output / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == '.html':
            text = path.read_text('utf-8')
            if path.name == 'index.html' and rel != Path('index.html') and rel.parent.name.startswith('yandex'):
                pass
            if '<html' not in text.lower():
                # verification file, copied byte-for-byte
                dest.write_bytes(path.read_bytes())
                continue
            report['pages'] += 1
            is_home = rel == Path('index.html')

            # Production robots policy is explicit. Preview stays noindex by HTML + Nginx header.
            robots = 'index,follow,max-image-preview:large' if mode == 'production' else 'noindex,nofollow'
            meta_robots = re.compile(r'<meta\b(?=[^>]*\bname=["\x27]robots["\x27])[^>]*>', re.I)
            if meta_robots.search(text):
                text = meta_robots.sub('<meta name="robots" content="'+robots+'">', text)
            else:
                text = re.sub(r'</head\s*>','<meta name="robots" content="'+robots+'"></head>',text,count=1,flags=re.I)

            # Footer and form placeholders must never be visible to clients after launch.
            text = text.replace('Проект нового сайта · действующий сайт не изменён','Юридическая помощь бизнесу и частным лицам')
            text = text.replace('Заявки работают после размещения на сервере M7Legal.','Мы свяжемся с вами после получения обращения.')
            text = text.replace('M7Legal — новая главная','M7Legal — сайт')
            text = text.replace('Новый сайт расширяет каталог на договорную работу, бизнес-споры, недвижимость и консультации.',
                                'Фирма объединяет договорную работу, бизнес-споры, недвижимость и консультации.')

            # Unified new-design header: no redundant dark utility strip;
            # display the email directly under the telephone. The original
            # Chinese landing page uses its independent legacy layout.
            if 'class="site-header"' in text and 'class="nav-phone"' in text:
                text = re.sub(
                    r'<div class="utility"><div class="wrap utility-inner">.*?</div></div>\s*',
                    '', text, count=1, flags=re.S,
                )
                if 'class="nav-contact"' not in text:
                    text, changed = re.subn(
                        r'(<div class="nav-actions">)(<a class="nav-phone"[^>]*>.*?</a>)',
                        lambda m: (m.group(1) + '<div class="nav-contact">' + m.group(2) +
                                   '<a class="nav-email" href="mailto:info@m7legal.ru">info@m7legal.ru</a></div>'),
                        text, count=1, flags=re.S,
                    )
                    if changed != 1:
                        raise ValueError('New-design header contact was not found: ' + str(rel))

            # References like #journal work only on the homepage; fix all non-existing fragment links.
            ids = set(re.findall(r'\bid=["\x27]([^"\x27]+)["\x27]', text))
            def fix_anchor(match):
                before, q, fragment = match.group(1), match.group(2), match.group(3)
                if fragment in ids: return match.group(0)
                return before + q + '/#' + fragment + q
            text = re.sub(r'(\bhref=)(["\x27])#([A-Za-z0-9_-]+)\2',fix_anchor,text)

            # Legacy pages and the homepage already fire click goals inline.
            # Mark those pages so site.js does not emit duplicate events.
            if 'reachGoal' in text and 'phone_click' in text:
                text = text.replace('<html ', '<html data-m7-inline-click-tracking="1" ', 1)

            # Every actual content page tracks calls and form-start once.
            if 'site.js' not in text:
                text = re.sub(r'</body\s*>','<script src="/site.js" defer></script></body>',text,count=1,flags=re.I)

            if mode == 'staging':
                # Remove lead sender, inline measurement pixels. No live network calls from preview.
                text = re.sub(r'<script\b[^>]*\bsrc=["\x27][^"\x27]*m7-form\.js[^"\x27]*["\x27][^>]*>\s*</script>', '', text, flags=re.I)
                text = re.sub(r'<!-- Yandex\.Metrika counter -->.*?<!-- /Yandex\.Metrika counter -->','',text,flags=re.I|re.S)
                text = re.sub(r'<noscript>\s*<div>\s*<img[^>]*mc\.yandex\.ru/watch[^>]*>\s*</div>\s*</noscript>','',text,flags=re.I|re.S)
                # Legacy inline analytics may be outside the named comment, but the tag guard in site.js
                # already limits new initialization to m7legal.ru. Remove explicit remote tag.js script.
                text = re.sub(r'<script\b[^>]*\bsrc=["\x27]https://mc\.yandex\.ru/[^"\x27]*["\x27][^>]*>\s*</script>', '',text,flags=re.I)
                # Preserve canonical pointing to production; client hyperlinks/assets stay on dev.
                canonical = re.search(r'<link\b(?=[^>]*\brel=["\x27]canonical["\x27])[^>]*>',text,flags=re.I)
                saved = canonical.group(0) if canonical else None
                if saved: text=text.replace(saved,'<!--M7_CANONICAL_SLOT-->')
                text = re.sub(r'(href|src)=(["\x27])/(?!/)',lambda m:m.group(1)+'='+m.group(2)+prefix, text)
                text = re.sub(r'(href|src)=(["\x27])https://m7legal\.ru/(?!/)',lambda m:m.group(1)+'='+m.group(2)+prefix,text)
                if saved:text=text.replace('<!--M7_CANONICAL_SLOT-->',saved)
                text = re.sub(r'<html\b', '<html data-preview-prefix="'+html.escape(prefix,quote=True)+'"',text,count=1,flags=re.I)
                text = re.sub(r'</head\s*>','<meta http-equiv="Content-Security-Policy" content="form-action \x27none\x27"></head>',text,count=1,flags=re.I)
                text = re.sub(r'</body\s*>','<script src="'+prefix+'preview.js" defer></script></body>',text,count=1,flags=re.I)
                if 'm7-form.js' in text:report['form_script_on_staging'].append(str(rel))
            else:
                if re.search(r'\bnoindex\b',text,flags=re.I):
                    report['noindex_release_pages'].append(str(rel))

            if not re.search(r'<script[^>]*\bsrc=["\x27][^"\x27]*site\.js',text,flags=re.I):
                report['missing_analytics_script'].append(str(rel))
            text = re.sub(r'((?:href|src)=)(["\x27])([^"\x27]*)\2', version_local_asset, text)
            dest.write_text(text,encoding='utf-8')
        elif path.suffix.lower() == '.css':
            css = path.read_text('utf-8')
            if mode == 'staging':
                css = re.sub(r'url\(\s*(["\x27]?)/(?!/)',lambda m:'url('+m.group(1)+prefix,css)
            dest.write_text(css,encoding='utf-8')
        else:
            shutil.copy2(path,dest)
        report['assets'] += 1

    # Deploy-safe defaults from a dedicated release source.
    robots_src = source / ('robots.production.txt' if mode == 'production' else 'robots.txt')
    shutil.copy2(robots_src, output/'robots.txt')
    if (source/'sitemap.production.xml').is_file():
        shutil.copy2(source/'sitemap.production.xml',output/'sitemap.xml')
    if mode == 'staging':
        (output/'preview.js').write_text(PREVIEW_JS,encoding='utf-8')

    # Validate local links and fragments in the actual emitted files.
    for page in output.rglob('*.html'):
        txt=page.read_text('utf-8')
        if '<html' not in txt.lower():continue
        ids=set(re.findall(r'\bid=["\x27]([^"\x27]+)["\x27]',txt))
        for raw in re.findall(r'\bhref=["\x27]([^"\x27]+)["\x27]',txt):
            if raw.startswith('#') and raw[1:] and raw[1:] not in ids:
                report['invalid_local_anchors'].append([str(page.relative_to(output)),raw])
            url=raw.split('#')[0].split('?')[0]
            if mode == 'staging' and url.startswith(prefix):
                url='/'+url[len(prefix):]
            elif mode == 'staging' and url.startswith('/'):
                # locally generated internal paths only
                if url.startswith('/api/'):continue
            if not url.startswith('/') or url.startswith('//'):continue
            if url in ('/',''):continue
            dest = output / url.lstrip('/')
            if not dest.is_file() and not (dest.is_dir() and (dest/'index.html').is_file()):
                report['broken_local_links'].append([str(page.relative_to(output)),raw])

    if report['invalid_local_anchors'] or report['broken_local_links'] or report['noindex_release_pages'] or report['form_script_on_staging'] or report['missing_analytics_script']:
        raise RuntimeError('Release validation failed: '+json.dumps(report,ensure_ascii=False)[:3200])
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--mode',required=True,choices=['staging','production'])
    p.add_argument('--prefix',default='/m7legal-preview-20261009/')
    a=p.parse_args()
    if a.mode=='staging' and (not a.prefix.startswith('/') or not a.prefix.endswith('/')):
        raise ValueError('Staging prefix must start/end with /')
    print(json.dumps(package(a.source.resolve(),a.output.resolve(),a.mode,a.prefix),ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
