import json, math, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_program_details(program):
    img_src = ''
    link = ''
    page_html = utils.get_url_html('https://www.npr.org/podcasts-and-shows/')
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('img', attrs={"alt": program})
    if el:
        img_src = el['src']
        it = el.find_parent('a')
        if it:
            link = it['href']
    return img_src, link


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    page_soup = BeautifulSoup(page_html, 'html.parser')
    el = page_soup.find('script', attrs={"type": "application/ld+json"})
    if not el:
        logger.warning('unable to find ld+json in ' + url)
        return None
    ld_json = json.loads(el.string)
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    npr_vars = None
    el = page_soup.find('script', id='npr-vars')
    if el:
        m = re.search(r'NPR\.serverVars =\s+({.*});$', el.string)
        if m:
            npr_vars = json.loads(m.group(1))

    item = {}
    if npr_vars:
        item['id'] = npr_vars['storyId']
    else:
        m = re.search(r'^/\d{4}/\d{2}/\d{2}/(\d+)/', urlsplit(url).path)
        if not m:
            logger.warning('unable to determine story id in ' + url)
            return None
        item['id'] = m.group(1)

    item['url'] = ld_json['mainEntityOfPage']['@id']
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(ld_json['dateModified']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if ld_json.get('author'):
        if isinstance(ld_json['author'], list):
            authors = ld_json['author']['name'].copy()
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        elif isinstance(ld_json['author'], dict):
            item['author']['name'] = ld_json['author']['name']
        elif isinstance(ld_json['author'], str):
            item['author']['name'] = ld_json['author']
    elif ld_json.get('publisher') and ld_json['publisher'].get('name'):
        item['author']['name'] = ld_json['publisher']['name']
    else:
        item['author']['name'] = 'NPR'

    item['tags'] = []
    if npr_vars:
        if npr_vars.get('tagIds'):
            item['tags'] += npr_vars['tagIds'].copy()
        if npr_vars.get('topics'):
            item['tags'] += npr_vars['topics'].copy()
        if npr_vars.get('programId'):
            item['tags'].append(npr_vars['programId'])

    if ld_json.get('image'):
        if isinstance(ld_json['image'], dict):
            item['_image'] = ld_json['image']['url']
        elif isinstance(ld_json['image'], list):
            item['_image'] = ld_json['image'][0]['url']

    if ld_json.get('description'):
        item['summary'] = ld_json['description']

    item['content_html'] = ''
    if '/player/' in url:
        el = page_soup.find('script', string=re.compile(r'audioModel'))
        if el:
            i = el.string.find('{')
            j = el.string.rfind('}') + 1
            audio_json = json.loads(el.string[i:j])
            poster = '{}/image?url={}&height=128&crop=128,128&overlay=audio'.format(config.server, item['_image'])
            item['content_html'] += '<table><tr><td><a href="{}"><img src="{}" /></a></td>'.format(audio_json['audioSrc'], poster)
            item['content_html'] += '<td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div><div>by {}</div>'.format(audio_json['storyUrl'], audio_json['title'], item['author']['name'])
            item['content_html'] += '<div style="font-size:0.9em;">{} &bull; {}</div>'.format(utils.format_display_date(dt, False), utils.calc_duration(audio_json['duration']))
            item['content_html'] += '</table>'
        if '/embed/' in url:
            return item

    text_html = utils.get_url_html('https://text.npr.org/' + item['id'])
    if not text_html:
        logger.warning('unable to get text content from ' + item['url'])
        return item

    text_soup = BeautifulSoup(text_html, 'html.parser')
    paragraphs = text_soup.find(class_='paragraphs-container')

    for el in paragraphs.find_all('hr'):
        if el.name == None:
            continue
        it = el.find_next_sibling()
        if it and it.name == 'a':
            if re.search(r'twitter\.com|youtube\.com', it['href']):
                new_html = utils.add_embed(it['href'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
                it_next = it.find_next_sibling()
                if it_next and it_next.name == 'hr':
                    it_next.decompose()
                it.decompose()

    story_text = page_soup.find(id='storytext')
    if story_text:
        for el in story_text.find_all(class_='bucketwrap'):
            new_html = ''
            if 'image' in el['class']:
                img_src = ''
                it = el.find('source')
                if it:
                    img_src = utils.image_from_srcset(it['srcset'], 1200)
                if not img_src:
                    it = el.find('img')
                    if it:
                        img_src = it['src']
                if img_src:
                    caption = ''
                    it = el.find(class_='caption')
                    if it and it.get_text().strip():
                        caption = it.get_text().strip()
                    new_html = utils.add_image(img_src, caption)
            elif 'pullquote' in el['class']:
                it = el.find(class_='byline')
                if it:
                    author = it.get_text().strip()
                else:
                    author = ''
                it = el.find(class_='bucket')
                new_html = utils.add_pullquote(it.decode_contents().strip(), author)
            elif 'statichtml' in el['class']:
                it = el.find('blockquote')
                if it:
                    if 'tiktok-embed' in it['class']:
                        new_html = utils.add_embed(it['cite'])
                    elif 'instagram-media' in it['class']:
                        new_html = utils.add_embed(it['data-instgrm-permalink'])
                if not new_html:
                    logger.warning('unhandled bucketwrap statichtml in ' + item['url'])
            elif 'internallink' in el['class'] and 'insettwocolumn' in el['class'] or 'twitter' in el['class'] or 'youtube-video' in el['class']:
                pass
            else:
                logger.warning('unhandled bucketwrap class {} in {}'.format(el['class'], item['url']))

            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                it = el.find_previous_sibling()
                if not it:
                    it = paragraphs.find('p')
                    it.insert_before(new_el)
                elif it.name == 'p':
                    txt = it.get_text().strip()[-50:]
                    for it in paragraphs.find_all('p'):
                        if it.get_text().strip().endswith(txt):
                            it.insert_after(new_el)
                            new_html = ''
                            break
                    if new_html:
                        logger.warning('unable to determine where to add bucketwrap element in ' + item['url'])

    el = page_soup.find(class_='audio-module-controls-wrap')
    if el:
        if el.get('data-audio'):
            audio_data = json.loads(el['data-audio'])
            attachment = {}
            attachment['url'] = audio_data['audioUrl']
            attachment['mime_type'] = 'audio/mpeg'
            item['attachments'] = []
            item['attachments'].append(attachment)
            item['_audio'] = audio_data['audioUrl']

            program_poster, program_link = get_program_details(audio_data['program'])
            if program_poster:
                poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(program_poster))
            else:
                poster = '{}/image?height=128&width=128&overlay=audio'.format(config.server)

            duration = []
            t = math.floor(float(audio_data['duration']) / 3600)
            if t >= 1:
                duration.append('{} hr'.format(t))
            t = math.ceil((float(audio_data['duration']) - 3600 * t) / 60)
            if t > 0:
                duration.append('{} min.'.format(t))

            new_html = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><a href="{}"><b>{}</b></a><br/><a href="{}"><small>{}</small></a><br/><small>{}&nbsp;&bull;&nbsp;{}</small></td></tr></table>'.format(audio_data['audioUrl'], poster, audio_data['storyUrl'], audio_data['title'], program_link, audio_data['program'], item['_display_date'], ', '.join(duration))

            new_el = BeautifulSoup(new_html, 'html.parser')
            it = paragraphs.find('p')
            it.insert_before(new_el)
        else:
            it = el.find(class_='audio-availability-message')
            if it:
                new_html = '<blockquote><b>{}</b></blockquote>'.format(it.get_text())
                new_el = BeautifulSoup(new_html, 'html.parser')
                it = paragraphs.find('p')
                it.insert_before(new_el)

    for el in paragraphs.find_all('a', href=re.compile('^/')):
        el['href'] = 'https://www.npr.com' + el['href']

    item['content_html'] += re.sub(r'<hr/>\s+Related Story: <a [^>]+>[^<]+</a>\s?<hr/>', '', paragraphs.decode_contents())
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
