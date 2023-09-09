import json, pytz, re
from bs4 import BeautifulSoup, NavigableString, Tag
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    soup = BeautifulSoup(page_html, 'lxml')
    meta = {}
    for el in soup.find_all('meta'):
        if el.get('property'):
            key = el['property']
        elif el.get('name'):
            key = el['name']
        else:
            continue
        if meta.get(key):
            if isinstance(meta[key], str):
                val = meta[key]
                meta[key] = []
                meta[key].append(val)
            meta[key].append(el['content'])
        else:
            if el.get('content'):
                meta[key] = el['content']
    if save_debug:
        utils.write_file(meta, './debug/meta.json')

    el = soup.find('script', attrs={"type": "application/ld+json"})
    if el:
        ld_json = json.loads(el.string)
        if save_debug:
            utils.write_file(ld_json, './debug/debug.json')
    else:
        ld_json = None

    item = {}
    item['id'] = paths[-1]

    if meta.get('og:url'):
        item['url'] = meta['og:url']
    elif ld_json and ld_json.get('mainEntityOfPage'):
        item['url'] = ld_json['mainEntityOfPage']['@id']

    if meta.get('og:title'):
        item['title'] = meta['og:title']
    elif meta.get('twitter:title'):
        item['title'] = meta['twitter:title']
    elif ld_json and ld_json.get('headline'):
        item['title'] = ld_json['headline']

    # Always EST?
    tz_loc = pytz.timezone('US/Eastern')
    if ld_json:
        dt_loc = datetime.fromisoformat(ld_json['datePublished'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt_loc = datetime.fromisoformat(ld_json['dateModified'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_modified'] = dt.isoformat()
    else:
        el = soup.find(class_='fdn-breadcrumb-release-date')
        if el:
            dt_loc = datetime.strptime(el.get_text().strip(), '%B %d, %Y')
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, False)
        else:
            el = soup.find(attrs={"data-component-id": "SlideshowAuthor"})
            if el:
                m = re.search(r'on (\w+, \w+ \d{1,2}, \d{4} at \d+:\d+ (am|pm))', el.get_text())
                if m:
                    dt_loc = datetime.strptime(m.group(1), '%a, %b %d, %Y at %I:%M %p')
                    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                    item['date_published'] = dt.isoformat()
                    item['_timestamp'] = dt.timestamp()
                    item['_display_date'] = utils.format_display_date(dt)

    if meta.get('author'):
        item['author'] = {"name": meta['author']}
    elif ld_json and ld_json.get('author'):
        item['author'] = {"name": ld_json['author']['name']}

    if meta.get('keywords'):
        item['tags'] = meta['keywords'].split(', ')
    elif meta.get('news_keywords'):
        item['tags'] = meta['news_keywords'].split(', ')

    if meta.get('og:image'):
        item['_image'] = meta['og:image']
    elif meta.get('thumbnail'):
        item['_image'] = meta['thumbnail']
    elif ld_json and ld_json.get('image'):
        item['_image'] = ld_json['image']['url']

    if meta.get('description'):
        item['summary'] = meta['description']
    elif meta.get('og:description'):
        item['summary'] = meta['og:description']
    elif ld_json and ld_json.get('description'):
        item['summary'] = ld_json['description']

    item['content_html'] = ''
    el = soup.find(class_='fdn-content-subheadline')
    if el:
        item['content_html'] += '<p><em>{}</em></p>'.format(el.get_text())

    el = soup.find(class_='fdn-content-header-image-block')
    if el:
        img = el.find('img')
        if img:
            captions = []
            it = el.find(class_='fdn-image-caption')
            if it and it.get_text().strip():
                captions.append(it.get_text().strip())
            it = el.find(class_='fdn-image-credit')
            if it and it.get_text().strip():
                captions.append(it.get_text().strip())
            if img.get('data-src'):
                img_src = img['data-src']
            else:
                img_src = img['src']
            img_paths = list(filter(None, urlsplit(img_src).path.split('/')))
            if 'imager' in img_paths:
                img_src = '{}/u/original/{}/{}'.format(site_json['imager'], img_paths[-2], img_paths[-1])
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
        else:
            logger.warning('unhandled fdn-content-header-image-block in ' + item['url'])

    el = soup.find(class_='fdn-magnum-block')
    if el:
        img = el.find('img')
        if img:
            captions = []
            it = el.find(class_='fdn-image-caption')
            if it and it.get_text().strip():
                captions.append(it.get_text().strip())
            it = el.find(class_='fdn-image-credit')
            if it and it.get_text().strip():
                captions.append(it.get_text().strip())
            if img.get('data-src'):
                img_src = img['data-src']
            else:
                img_src = img['src']
            img_paths = list(filter(None, urlsplit(img_src).path.split('/')))
            if 'imager' in img_paths:
                img_src = '{}/u/original/{}/{}'.format(site_json['imager'], img_paths[-2], img_paths[-1])
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
        else:
            logger.warning('unhandled fdn-magnum-block in ' + item['url'])

    body = soup.find(class_='fdn-content-body')
    if body:
        for el in body.find_all(id=re.compile(r'ad-slot')):
            el.decompose()

        for el in body.find_all('script'):
            el.decompose()

        for el in body.find_all('span', attrs={"style": re.compile(r'font-family')}):
            el.unwrap()

        for el in body.find_all('span', class_='__cf_email__'):
            el.unwrap()

        for el in body.find_all('br', class_='Apple-interchange-newline'):
            el.decompose()

        def fix_div(el):
            for it in el.contents:
                if isinstance(it, NavigableString) and it.strip():
                    #print('NavigableString: ' + it.strip())
                    el.name = 'p'
                    new_html = re.sub(r'\s*<br/>\s*<br/>\s*', '</p><p>', str(el))
                    el.replace_with(BeautifulSoup(new_html, 'html.parser'))
                    break
                elif isinstance(it, Tag):
                    #print('Tag: ' + it.name)
                    if it.name == 'div' and not it.get('class'):
                        fix_div(it)
                    if re.search(r'\b(blockquote|br|div|h\d|ol|p|ul)\b', it.name):
                        el.unwrap()
                    else:
                        el.name = 'p'
                    break

        for el in body.find_all('div', class_=False, recursive=False):
            fix_div(el)

        for el in body.find_all(attrs={"style": True}):
            del el['style']

        for el in body.contents:
            if isinstance(el, NavigableString) and el.strip():
                el.replace_with(BeautifulSoup('<p>{}</p>'.format(el), 'html.parser'))

        p = None
        for el in body.find_all(recursive=False):
            if el.name == None:
                continue
            elif el.name == 'br':
                el.decompose()
            elif not re.search(r'\b(blockquote|div|h\d|ol|p|ul)\b', el.name):
                p = el.find_previous_sibling()
                if p.name == 'p':
                    p.append(el)
                else:
                    p = None
                    if el.name == 'i':
                        el.wrap(soup.new_tag('p'))
            elif p:
                if el.name == 'p':
                    p.extend(el.contents)
                    el.decompose()
                p = None

        for el in body.find_all('a', href=re.compile(r'^/')):
            el['href'] = '{}:{}{}'.format(split_url.scheme, split_url.netloc, el['href'])

        for el in body.find_all(class_=re.compile(r'fdn-content-image')):
            img = el.find('img')
            if img:
                captions = []
                it = el.find(class_='fdn-image-caption')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                it = el.find(class_='fdn-image-credit')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                if img.get('data-src'):
                    img_src = img['data-src']
                else:
                    img_src = img['src']
                img_paths = list(filter(None, urlsplit(img_src).path.split('/')))
                if 'imager' in img_paths:
                    img_src = '{}/u/original/{}/{}'.format(site_json['imager'], img_paths[-2], img_paths[-1])
                new_html = utils.add_image(img_src, ' | '.join(captions))
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled fdn-content-image in ' + item['url'])

        for el in body.find_all(class_='twitter-tweet'):
            links = el.find_all('a', href=re.compile(r'twitter\.com/[^/]+/status'))
            new_html = utils.add_embed(links[-1]['href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all(class_='instagram-media'):
            new_html = utils.add_embed(el['data-instgrm-permalink'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all(class_='tiktok-embed'):
            new_html = utils.add_embed(el['cite'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all(class_='fb_iframe_widget '):
            new_html = utils.add_embed(el['data-href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in body.find_all('blockquote', class_=False):
            el['style'] = 'border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;'

        for el in body.find_all(class_='fdn-inline-connection'):
            new_html = ''
            title = el.find(class_='fdn-inline-connection-title')
            if title:
                if re.search(r'related', title.get_text(), flags=re.I):
                    el.decompose()
                    continue
                elif re.search(r'slideshow', title.get_text(), flags=re.I):
                    title = el.find(class_='fdn-inline-connection-headline')
                    new_html = '<div style="overflow:hidden;"><span style="font-size:0.9em; font-weight:bold;">Slideshow</span><br/><span style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></span></div>'.format(title.a['href'], title.get_text().strip())
                    img = el.find('img')
                    if img:
                        if img.get('data-src'):
                            img_src = img['data-src']
                        else:
                            img_src = img['src']
                        new_html = '<div><a href="{}"><img src="{}" style="width:128px; float:left; margin-right:8px;" /></a>'.format(title.a['href'], img_src) + new_html + '<div style="clear:left;"></div></div>'
                elif re.search(r'details', title.get_text(), flags=re.I):
                    # Event details: https://www.cltampa.com/music/beyonces-world-tour-is-coming-to-tampa-this-summer-15042029
                    # Film details: https://www.metrotimes.com/arts/indie-horror-flick-skinamarink-is-a-surreal-hit-experienced-through-the-eyes-of-children-32270351
                    new_html = '<div style="overflow:hidden;"><span style="font-size:0.9em; font-weight:bold;">{}</span><br/>'.format(title.get_text().strip())
                    title = el.find(class_='fdn-inline-connection-headline')
                    new_html += '<span style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></span>'.format(title.a['href'], title.get_text().strip())
                    for it in el.find_all(class_='fdn-teaser-infoline'):
                        if re.search(r'-split', ','.join(it['class'])):
                            captions = []
                            for s in it.find_all(['p', 'span']):
                                if s.get_text().strip():
                                    captions.append(s.decode_contents().strip())
                            new_html += '<br/><small>{}</small>'.format(' | '.join(captions))
                        else:
                            new_html += '<br/><small>{}</small>'.format(it.decode_contents().strip())
                    new_html += '</div>'
                    img = el.find('img')
                    if img:
                        if img.get('data-src'):
                            img_src = img['data-src']
                        else:
                            img_src = img['src']
                        new_html = '<br/><div><a href="{}"><img src="{}" style="width:128px; float:left; margin-right:8px;" /></a>'.format(title.a['href'], img_src) + new_html + '<div style="clear:left;"></div></div>'

                elif re.search(r'pdf', title.get_text(), flags=re.I):
                    # https://www.clevescene.com/news/neighbors-battle-over-cleveland-heights-couples-backyard-pizza-oven-goes-to-trial-this-week-and-sets-a-street-on-edge-41302239
                    new_html = '<p><span style="font-size:1.5em;">&#10515;</span>&nbsp;<b>Download: <a href="{}">{}</a></b></p>'.format(title.a['href'], title.get_text().strip())
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled fdn-inline-connection in ' + item['url'])

        for el in body.find_all('iframe'):
            new_html = utils.add_embed(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    item['content_html'] += body.decode_contents()

    if 'Slideshow' in paths:
        item['content_html'] += '<div>&nbsp;</div>'
        for el in soup.find_all(class_='fdn-slideshow-image-block'):
            if el.find(class_='twitter-tweet'):
                links = el.find_all('a', href=re.compile(r'twitter\.com/[^/]+/status'))
                item['content_html'] += utils.add_embed(links[-1]['href'])
            elif el.find('img'):
                captions = []
                it = el.find(class_='fdn-slideshow-caption')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                it = el.find(class_='fdn-slideshow-credit')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                img = el.find('img')
                if img.get('data-src'):
                    img_src = img['data-src']
                else:
                    img_src = img['src']
                img_paths = list(filter(None, urlsplit(img_src).path.split('/')))
                if 'imager' in img_paths:
                    img_src = '{}/u/original/{}/{}'.format(site_json['imager'], img_paths[-2], img_paths[-1])
                item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
            else:
                logger.warning('unhandled slideshow-image-block in ' + item['url'])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
