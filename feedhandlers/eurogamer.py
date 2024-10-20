import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    return '{}://{}{}?width={}&quality=80&format=jpg&auto=webp'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def add_bluebillywig_video(script_src, caption):
    script_js = utils.get_url_html(script_src)
    if not script_js:
        return ''
    m = re.search(r'var opts\s?=\s?(\{.*?\});\n', script_js)
    if not m:
        logger.warning('unable to parse bluebillywig video opts in ' + script_src)
        return None
    video_json = json.loads(m.group(1))
    utils.write_file(video_json, './debug/video.json')
    videos = []
    for video in video_json['clipData']['assets']:
        if re.search(r'MP4', video['mediatype'], flags=re.I):
            video['mimetype'] = 'video/mp4'
            video['bandwidth'] = int(video['bandwidth'])
            video['src'] = video_json['publicationData']['defaultMediaAssetPath'] + video['src']
            videos.append(video)
    video = utils.closest_dict(videos, 'bandwidth', 1600)
    posters = []
    for poster in video_json['clipData']['thumbnails']:
        poster['width'] = int(poster['width'])
        poster['src'] = video_json['publicationData']['defaultMediaAssetPath'] + poster['src']
        posters.append(poster)
    poster = utils.closest_dict(posters, 'width', 1080)
    if caption:
        video_caption = '{} | Watch: {}'.format(caption, video_json['clipData']['title'])
    else:
        video_caption = video_json['clipData']['title']
    if video:
        return utils.add_video(video['src'], video['mimetype'], poster['src'], video_caption)
    elif video_json['clipData'].get('importUrl') and re.search(r'youtube\.com', video_json['clipData']['importUrl']):
        return utils.add_embed(video_json['clipData']['importUrl'])
    return ''


def get_content(url, args, site_json, save_debug=False, module_format_content=None):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'lxml')
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json = json.loads(el.string)
        if ld_json.get('@type') and (ld_json['@type'] == 'NewsArticle' or ld_json['@type'] == 'Review'):
            break
        else:
            ld_json = None

    if not ld_json:
        logger.warning('unable to find ld+json in ' + url)
        return None

    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    item = {}
    item['id'] = ld_json['url']
    item['url'] = ld_json['url']
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified'])
        item['date_modified'] = dt.isoformat()

    if isinstance(ld_json['author'], dict):
        item['author'] = {
            "name": ld_json['author']['name']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
    elif isinstance(ld_json['author'], list):
        item['authors'] = [{"name": x['name'].replace(',', '&#44;')} for x in ld_json['author']]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']])).replace('&#44;', ',')
        }

    if ld_json.get('keywords'):
        item['tags'] = ld_json['keywords'].copy()

    if ld_json.get('image'):
        item['image'] = ld_json['image'][0]

    if ld_json.get('description'):
        item['summary'] = ld_json['description']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    el = soup.find('p', class_='strapline')
    if el:
        item['content_html'] += '<p><em>{}</em></p>'.format(el.decode_contents())

    el = soup.find('figure', class_='headline_image_wrapper')
    if el:
        if el.figcaption:
            caption = el.figcaption.get_text()
        else:
            caption = ''
        if el.a:
            item['content_html'] += utils.add_image(el.a['href'], caption)

    content = soup.find(class_='article_body_content')
    if not content:
        logger.warning('unable to find article_body_content in ' + item['url'])
        return item
    if save_debug:
        utils.write_file(str(content), './debug/debug.html')

    while content:
        for el in content.find_all(['button', 'noscript', 'poll_wrapper', 'style']):
            el.decompose()
        for el in content.find_all('aside', class_='recommendation'):
            el.decompose()
        for el in content.find_all(class_=['apester-media', 'apester-unit', 'desktop_mpu', 'injection_placeholder']):
            el.decompose()
        for el in content.find_all(attrs={"data-type": "targeting"}):
            el.decompose()

        for el in content.find_all('table'):
            if el.find('img', src=re.compile(r'Game-Pass_EIr0ikp|Amazon-Prime_wGIKZ2n')):
                el.decompose()

        for el in soup.select('p > figure'):
            el.parent.unwrap()
        for el in soup.select('p > div.twitter-tweet'):
            el.parent.unwrap()

        for el in soup.select('ul > figure'):
            # https://www.vg247.com/the-best-games-ever-show-episode-53
            new_html = '<ul>'
            for it in el.parent.find_all('li'):
                new_html += str(it)
                it.decompose()
            new_html += '</ul>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.parent.insert_after(new_el)
            el.parent.unwrap()

        for el in content.find_all('section', class_=False):
            el.unwrap()
        for el in content.find_all('section', class_='table-of-contents'):
            el.unwrap()
        for el in content.find_all('section', class_='endnote'):
            el.insert(0, soup.new_tag('hr'))
            el.unwrap()

        for el in content.find_all('bloc'
                                   'kquote', class_='pullquote', recursive=False):
            if el.cite:
                author = el.cite.decode_contents()
                el.cite.decompose()
                new_html = utils.add_pullquote(el.decode_contents(), author)
            else:
                new_html = utils.add_pullquote(el.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in content.find_all('blockquote', class_=False, recursive=False):
            if not el.find('a', href=re.compile(r'www\.gamesindustry\.biz/newsletters')):
                new_html = utils.add_blockquote(el.decode_contents())
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
            el.decompose()

        for el in content.find_all('aside', recursive=False):
            if el.blockquote:
                new_html = utils.add_blockquote(el.blockquote.decode_contents())
            else:
                new_html = utils.add_blockquote(el.decode_contents())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in content.find_all(class_='review_rating'):
            new_html = '<div style="font-size:3em; text-align:center;">'
            for it in el.find_all(class_='star'):
                if 'disabled' in it['class']:
                    new_html += '☆'
                else:
                    new_html += '★'
            new_html += '</div>'
            it = content.find(class_='synopsis')
            if it:
                new_html += '<div style="font-size:1.1em; font-weight:bold; text-align:center;">{}</div>'.format(it.decode_contents())
                it.decompose()
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in content.find_all('figure', recursive=False) + content.find_all('div', class_=['blue_billywig', 'embed_wrapper'], recursive=False):
            #print(el)
            new_html = ''
            if el.figcaption:
                caption = el.figcaption.decode_contents()
            else:
                caption = ''
            if el.find(class_='video_wrapper') or (el.get('class') and 'video_wrapper' in el['class']):
                it = el.find('script', attrs={"data-cookies-src": re.compile(r'gamernetwork\.bbvms\.com')})
                if it:
                    new_html += add_bluebillywig_video(it['data-cookies-src'], caption)
                else:
                    it = el.find('a', attrs={"href": re.compile(r'youtube\.com')})
                    if it:
                        new_html += utils.add_embed(it['href'])
                    else:
                        it = el.find('iframe')
                        if it:
                            if it.get('src'):
                                new_html += utils.add_embed(it['src'])
                            elif it.get('data-src'):
                                new_html += utils.add_embed(it['data-src'])
            elif el.find(class_='embed_wrapper') or (el.get('class') and 'embed_wrapper' in el['class']):
                it = el.find('iframe')
                if it:
                    if it.get('src'):
                        new_html += utils.add_embed(it['src'])
                    elif it.get('data-src'):
                        new_html += utils.add_embed(it['data-src'])
            elif el.get('role') and el['role'] == 'group':
                if el['data-count'] == '0':
                    images = el.find_all('a')
                else:
                    images = el.find_all('figure')
                for i, it in enumerate(reversed(images)):
                    if i == 0:
                        if it.name == 'figure':
                            if it.figcaption:
                                caption = it.figcaption.decode_contents()
                            img_src = it.a['href']
                        else:
                            img_src = it['href']
                        new_html += utils.add_image(resize_image(img_src), caption)
                    else:
                        if it.name == 'figure':
                            if it.figcaption:
                                caption = it.figcaption.decode_contents()
                            else:
                                caption = ''
                            img_src = it.a['href']
                        else:
                            img_src = it['href']
                            caption = ''
                        new_html = utils.add_image(resize_image(img_src), caption) + new_html
            elif el.find(class_='content_image'):
                if el.figcaption:
                    caption = el.figcaption.decode_contents()
                else:
                    caption = ''
                if el.a:
                    new_html += utils.add_image(resize_image(el.a['href']), caption)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled figure in ' + item['url'])

        for el in content.find_all(class_='gallery', recursive=False):
            new_html = ''
            for it in el.find_all('a', class_='thumbnail'):
                new_html += utils.add_image(resize_image(it['href']))
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled gallery in ' + item['url'])

        for el in content.find_all(class_='reddit-embed-bq', recursive=False):
            links = el.find_all('a')
            new_html = utils.add_embed(links[0]['href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in content.find_all('blockquote', class_='tiktok-embed', recursive=False):
            new_html = utils.add_embed(el['cite'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in content.find_all(class_=['twitter-tweet', 'twitter_wrapper'], recursive=False):
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in content.find_all('section', class_='digital_foundry_graph', recursive=False):
            new_html = ''
            it = el.find(class_='section_title')
            if it:
                new_html += '<h2>{}</h2>'.format(it.get_text())
            it = el.find(class_='data-source', attrs={"data-video-id": True})
            if it:
                new_html += utils.add_embed('https://www.youtube.com/watch?v={}'.format(it['data-video-id']))
            labels = []
            values = []
            for it in el.find_all(class_='data'):
                if it.get('data-resolution'):
                    labels.append('{} ({})'.format(it['data-label'], it['data-resolution']))
                else:
                    labels.append(it['data-label'])
                values.append(float(it['data-mean-average']))
            max_val = max(values)
            new_html += '<div>&nbsp;</div><div style="width:80%; margin-right:auto; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px; padding:10px;">'
            for i, val in enumerate(values):
                pct = int(val / max_val * 100)
                if pct >= 50:
                    new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to right, lightblue {}%, white {}%);"><p><b>{}</b></p><p>{}</p></div>'.format(pct, 100 - pct, labels[i], val)
                else:
                    new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to left, white {}%, lightblue {}%);"><p><b>{}</b></p><p>{}</p></div>'.format(100 - pct, pct, labels[i], val)
            new_html += '</div>'
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in content.find_all('script'):
            el.decompose()

        item['content_html'] += content.decode_contents()

        if soup.find(class_='paywall'):
            item['content_html'] += '<h2 style="text-align:center; color:red;">A subscription is requrired to read this article</h2>'

        content = None
        el = soup.find(class_='next')
        if el and el.a:
            if save_debug:
                logger.debug('addition addition content from ' + el.a['href'])
            page_html = utils.get_url_html(item['url'] + el.a['href'])
            if page_html:
                soup = BeautifulSoup(page_html, 'lxml')
                content = soup.find(class_='article_body_content')

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if url.endswith('feed'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) > 1:
        logger.warning('unsupported feed url ' + url)
        return None
    page_html = utils.get_url_html('{}://{}/archive{}'.format(split_url.scheme, split_url.netloc, split_url.path))
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    article_list = soup.find('ul', class_='summary_list')
    if not article_list:
        logger.warning('unable to find summary_list for ' + url)
        return None

    n = 0
    feed_items = []
    for el in article_list.find_all('li'):
        link = el.find(class_='link_overlay')
        if link:
            if save_debug:
                logger.debug('getting content for ' + link['href'])
            item = get_content(link['href'], args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    feed = utils.init_jsonfeed(args)
    feed['title'] = '{} | {}'.format(paths[0].title(), split_url.netloc)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
