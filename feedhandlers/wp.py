import copy, html, json, pytz, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False, module_format_content=None):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) > 0 and paths[-1] == 'embed':
        args['embed'] = True
        del paths[-1]
        page_url = '{}://{}/{}'.format(split_url.scheme, split_url.netloc, '/'.join(paths))
    else:
        page_url = url
    base_url = '{}://{}'.format(split_url.scheme, split_url.netloc)

    page_html = utils.get_url_html(page_url, site_json=site_json)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    if save_debug:
        utils.write_file(soup.prettify(), './debug/debug.html')

    meta = {}
    for el in soup.find_all('meta'):
        if not el.get('content'):
            continue
        if el.get('property'):
            key = el['property']
        elif el.get('name'):
            key = el['name']
        else:
            continue
        if meta.get(key):
            if isinstance(meta[key], str):
                if meta[key] != el['content']:
                    val = meta[key]
                    meta[key] = []
                    meta[key].append(val)
            if el['content'] not in meta[key]:
                meta[key].append(el['content'])
        else:
            meta[key] = el['content']
    if save_debug:
        utils.write_file(meta, './debug/meta.json')

    ld_json = []
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        try:
            ld = json.loads(el.string)
            if isinstance(ld, list):
                for it in ld:
                    if it.get('@graph'):
                        ld_json += it['@graph'].copy()
                    elif it.get('@type'):
                        ld_json.append(it)
            elif isinstance(ld, dict):
                if ld.get('@graph'):
                    ld_json += ld['@graph'].copy()
                elif ld.get('@type'):
                    ld_json.append(ld)
        except:
            logger.warning('unable to convert ld+json in ' + page_url)
            pass
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    article_json = None
    ld_page = None
    ld_article = None
    ld_people = []
    ld_images = []
    for ld in ld_json:
        if isinstance(ld, dict):
            it = ld
            if not it.get('@type'):
                continue
            if isinstance(it['@type'], str):
                if it['@type'] == 'WebPage':
                    ld_page = it
                elif not article_json and 'Article' in it['@type']:
                    ld_article = it
                elif not article_json and it['@type'] == 'Product' and it.get('Review'):
                    ld_article = it['Review']
                elif it['@type'] == 'Person':
                    ld_people.append(it)
                elif it['@type'] == 'ImageObject':
                    ld_images.append(it)
            elif isinstance(it['@type'], list):
                if 'WebPage' in it['@type']:
                    ld_page = it
                elif not article_json and re.search(r'Article', '|'.join(it['@type'])):
                    article_json = it
                    ld_article = it
        elif isinstance(ld, list):
            for it in ld:
                if not it.get('@type'):
                    continue
                if isinstance(it['@type'], str):
                    if it['@type'] == 'WebPage':
                        ld_page = it
                    elif not article_json and 'Article' in it['@type']:
                        ld_article = it
                    elif not article_json and it['@type'] == 'Product' and it.get('Review'):
                        ld_article = it['Review']
                    elif it['@type'] == 'Person':
                        ld_people.append(it)
                    elif it['@type'] == 'ImageObject':
                        ld_images.append(it)
                elif isinstance(it['@type'], list):
                    if 'WebPage' in it['@type']:
                        ld_page = it
                    elif not article_json and re.search(r'Article', '|'.join(it['@type'])):
                        article_json = it

    if ld_article:
        article_json = ld_article
    elif ld_page:
        article_json = ld_page

    el = soup.find('link', attrs={"rel": "alternative", "type": "application/json+oembed"})
    if el:
        oembed_json = utils.get_url_json(el['href'])
    else:
        oembed_json = None

    if site_json.get('wpjson_path') and 'embed' not in args:
        args_copy = args.copy()
        args_copy['embed'] = True
        item = wp_posts.get_content(page_url, args_copy, site_json, save_debug)
    else:
        item = {}

    if not item.get('id'):
        el = soup.find('link', attrs={"rel": "shortlink"})
        if el:
            item['url'] = el['href']
            m = re.search(r'p=(\d+)', urlsplit(el['href']).query)
            if m:
                item['id'] = m.group(1)

        if not item.get('id'):
            el = soup.find(id=re.compile(r'post-\d+'))
            if el:
                m = re.search(r'post-(\d+)', el['id'])
                if m:
                    item['id'] = m.group(1)

        if not item.get('id'):
            m = re.search(r'"articleId","(\d+)"', page_html)
            if m:
                item['id'] = m.group(1)

        if not item.get('id') and article_json and article_json.get('@id'):
            item['id'] = article_json['@id']

    if not item.get('url'):
        if meta and meta.get('og:url'):
            item['url'] = meta['og:url']
        elif article_json and article_json.get('url'):
            item['url'] = article_json['url']
        elif article_json and article_json.get('mainEntityOfPage'):
            if isinstance(article_json['mainEntityOfPage'], str):
                item['url'] = article_json['mainEntityOfPage']
            elif isinstance(article_json['mainEntityOfPage'], dict):
                item['url'] = article_json['mainEntityOfPage']['@id']
        else:
            el = soup.find('link', attrs={"rel": "canonical"})
            if el:
                item['url'] = el['href']
            else:
                item['url'] = page_url

    if not item.get('id') and item.get('url'):
        item['id'] = item['url']

    if not item.get('title'):
        if site_json.get('title'):
            el = soup.find(site_json['title']['tag'], attrs=site_json['title']['attrs'])
            if el:
                item['title'] = el.get_text().strip()
        if not item.get('title'):
            if article_json and article_json.get('headline'):
                item['title'] = article_json['headline']
            elif meta and meta.get('og:title'):
                if isinstance(meta['og:title'], list):
                    item['title'] = meta['og:title'][0]
                else:
                    item['title'] = meta['og:title']
            elif meta and meta.get('twitter:title'):
                if isinstance(meta['twitter:title'], list):
                    item['title'] = meta['twitter:title'][0]
                else:
                    item['title'] = meta['twitter:title']
            elif oembed_json and oembed_json['title']:
                item['title'] = oembed_json['title']
            elif article_json and article_json.get('name'):
                item['title'] = article_json['name']
        if not item.get('title'):
            item['title'] = soup.title.get_text()
        item['title'] = item['title'].replace('&amp;', '&')
        if item.get('title') and re.search(r'#\d+|&\w+;', item['title']):
            item['title'] = html.unescape(item['title'])
        if site_json.get('site_title') and site_json['site_title'] in item['title']:
            item['title'] = re.sub(r'(.*)\s+[–-]\s+{}'.format(site_json['site_title']), r'\1', item['title'])

    if not item.get('date_published'):
        date = ''
        if meta and meta.get('article:published_time'):
            if isinstance(meta['article:published_time'], list):
                date = meta['article:published_time'][0]
            else:
                date = meta['article:published_time']
        elif article_json and article_json.get('datePublished'):
            date = article_json['datePublished']
        else:
            el = soup.find('time', attrs={"datetime": True})
            if el:
                date = el['datetime']
                if not re.search(r'[+\-]\d{2}:?\d{2}', date):
                    if site_json.get('timezone'):
                        dt_loc = datetime.fromisoformat(date)
                        tz_loc = pytz.timezone(site_json['timezone'])
                        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                        date = dt.isoformat()
                    else:
                        date += '+00:00'
        if date:
            try:
                if date.isnumeric():
                    dt = datetime.fromtimestamp(int(date)).replace(tzinfo=timezone.utc)
                else:
                    dt = datetime.fromisoformat(date).astimezone(timezone.utc)
            except:
                dt = dateutil.parser.parse(date)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
        elif site_json.get('date'):
            # This is for displaying content, the real date to be substituted from the rss feed
            for el in utils.get_soup_elements(site_json['date'], soup):
                item['_display_date'] = el.get_text()
                break

    if not item.get('date_modified'):
        date = ''
        if meta and meta.get('article:modified_time'):
            if isinstance(meta['article:modified_time'], list):
                date = meta['article:modified_time'][0]
            else:
                date = meta['article:modified_time']
        elif meta and meta.get('og:updated_time'):
            if isinstance(meta['og:updated_time'], list):
                date = meta['og:updated_time'][0]
            else:
                date = meta['og:updated_time']
        elif article_json and article_json.get('dateModified'):
            date = article_json['dateModified']
        if date:
            dt = datetime.fromisoformat(date).astimezone(timezone.utc)
            item['date_modified'] = dt.isoformat()

    if not item.get('author'):
        authors = []
        if site_json.get('author'):
            for el in utils.get_soup_elements(site_json['author'], soup):
                author = ''
                if el.name == 'meta':
                    author = el['content']
                elif el.name == 'a':
                    author = el.get_text().strip()
                else:
                    for it in el.find_all('a', href=re.compile(r'author|correspondents|staff')):
                        author = it.get_text().strip()
                        if author not in authors:
                            authors.append(author)
                if not authors and el.get_text().strip():
                    author = re.sub(r'^By:?\s*', '', el.get_text().strip(), flags=re.I)
                if author:
                    author = re.sub(r'(.*?),\s?Associated Press$', r'\1 (Associated Press)', author)
                    if author not in authors:
                        authors.append(author)
                if authors and not site_json['author'].get('multi'):
                    break
        elif article_json and article_json.get('author'):
            if isinstance(article_json['author'], dict):
                if article_json['author'].get('name'):
                    authors.append(article_json['author']['name'].replace(',', '&#44;'))
            elif isinstance(article_json['author'], list):
                for it in article_json['author']:
                    if it.get('name'):
                        authors.append(it['name'].replace(',', '&#44;'))
        if not authors and ld_people:
            if ld_people:
                for it in ld_people:
                    authors.append(it['name'].replace(',', '&#44;'))
        if not authors and meta:
            if meta.get('author'):
                authors.append(meta['author'].replace(',', '&#44;'))
            elif meta.get('citation_author'):
                authors.append(meta['citation_author'].replace(',', '&#44;'))
            elif meta.get('parsely-author'):
                authors.append(meta['parsely-author'].replace(',', '&#44;'))
        if not authors and oembed_json and oembed_json.get('author_name'):
                authors.append(oembed_json['author_name'].replace(',', '&#44;'))
        if not authors and site_json.get('authors'):
            authors.append(site_json['authors']['default'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)).replace('&#44;', ',')
        elif site_json.get('authors'):
            item['author'] = {"name": site_json['authors']['default']}

    if not item.get('tags'):
        item['tags'] = []
        if site_json.get('tags'):
            for el in utils.get_soup_elements(site_json['tags'], soup):
                if el.name == 'a':
                    item['tags'].append(el.get_text().strip())
                else:
                    for it in el.find_all('a'):
                        item['tags'].append(it.get_text().strip())
        elif article_json and article_json.get('keywords'):
            if isinstance(article_json['keywords'], list):
                item['tags'] = article_json['keywords'].copy()
            elif isinstance(article_json['keywords'], str):
                # Split & remove whitespace: https://stackoverflow.com/questions/4071396/split-by-comma-and-strip-whitespace-in-python
                item['tags'] = list(map(str.strip, article_json['keywords'].split(',')))
        elif meta and meta.get('article:tag'):
            if isinstance(meta['article:tag'], list):
                item['tags'] = meta['article:tag'].copy()
            elif isinstance(meta['article:tag'], str):
                item['tags'] = list(map(str.strip, meta['article:tag'].split(',')))
        elif meta and meta.get('parsely-tags'):
            item['tags'] = list(map(str.strip, meta['parsely-tags'].split(',')))
        elif meta and meta.get('keywords'):
            item['tags'] = list(map(str.strip, meta['keywords'].split(',')))
        elif article_json and article_json.get('articleSection') and isinstance(article_json['articleSection'], list):
            item['tags'] = article_json['articleSection'].copy()
        if not item.get('tags'):
            del item['tags']
        else:
            # Remove duplicates (case-insensitive)
            item['tags'] = list(dict.fromkeys([it.casefold() for it in item['tags']]))

    if not item.get('_image'):
        if ld_images:
            item['_image'] = ld_images[0]['url']
        if not item.get('_image') and article_json:
            if article_json.get('image'):
                if isinstance(article_json['image'], dict):
                    if article_json['image'].get('url'):
                        item['_image'] = article_json['image']['url']
                elif isinstance(article_json['image'], str):
                    item['_image'] = article_json['image']
            if not item.get('_image') and article_json.get('thumbnailUrl'):
                item['_image'] = article_json['thumbnailUrl']
        if not item.get('_image') and meta and meta.get('og:image'):
            if isinstance(meta['og:image'], str):
                item['_image'] = meta['og:image']
            else:
                item['_image'] = meta['og:image'][0]
        elif oembed_json and oembed_json.get('thumbnail_url'):
            item['_image'] = oembed_json['thumbnail_url']

    if article_json and article_json.get('description'):
        item['summary'] = article_json['description']
    elif oembed_json and oembed_json.get('description'):
        item['summary'] = oembed_json['description']
    elif meta and meta.get('description'):
        item['summary'] = meta['description']
    elif meta and meta.get('og:description'):
        item['summary'] = meta['og:description']
    elif meta and meta.get('twitter:description'):
        item['summary'] = meta['twitter:description']

    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(split_url.netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
        return item

    gallery = ''
    item['content_html'] = ''
    if site_json.get('subtitle'):
        subtitles = []
        for el in utils.get_soup_elements(site_json['subtitle'], soup):
            subtitles.append(el.get_text())
        if subtitles:
            item['content_html'] += '<p><em>{}</em></p>'.format('<br/>'.join(subtitles))
    elif 'add_subtitle' in args and item.get('summary'):
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    if 'add_lede_img' in args:
        if 'no_lede_caption' in args:
            add_caption = False
        else:
            add_caption = True
        lede = False
        if site_json.get('lede_video'):
            elements = utils.get_soup_elements(site_json['lede_video'], soup)
            if elements:
                el = elements[0]
                if el:
                    it = el.find(class_='jw-video-box')
                    if it:
                        item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/v2/media/{}'.format(it['data-video']))
                        lede = True
                    else:
                        it = el.find(id=re.compile(r'jw-player-'))
                        if it:
                            if article_json.get('video'):
                                item['content_html'] += utils.add_embed(article_json['video']['embedUrl'])
                                lede = True
                            else:
                                it = soup.find('script', string=re.compile(r'jwplayer\("{}"\)\.setup\('.format(it['id'])))
                                if it:
                                    m = re.search(r'"mediaid":"([^"]+)"', it.string)
                                    if m:
                                        item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/v2/media/{}'.format(m.group(1)))
                                        lede = True
                        else:
                            it = el.find(class_='video-wrapper')
                            if it and it.get('data-type') and it['data-type'] == 'youtube':
                                item['content_html'] += utils.add_embed(it['data-src'])
                                lede = True
                            else:
                                it = el.find('iframe')
                                if it:
                                    item['content_html'] += utils.add_embed(it['src'])
                                    lede = True
                                else:
                                    logger.warning('unhandled lede video wrapper in ' + item['url'])
        if not lede and site_json.get('lede_img'):
            elements = utils.get_soup_elements(site_json['lede_img'], soup)
            if elements:
                el = elements[0]
                if el:
                    if el.find(class_='rslides'):
                        it = el.find('li')
                        item['content_html'] += wp_posts.add_image(copy.copy(it), None, base_url, site_json, add_caption=add_caption)
                        lede = True
                        gallery = wp_posts.format_content(str(el), item, site_json, module_format_content)
                    elif el.find('img'):
                        item['content_html'] += wp_posts.add_image(el, None, base_url, site_json, add_caption=add_caption)
                        lede = True
                    else:
                        it = el.find('iframe')
                        if it:
                            item['content_html'] += utils.add_embed(it['src'])
                            lede = True
        if not lede and item.get('_image'):
            item['content_html'] += utils.add_image(wp_posts.resize_image(item['_image'], site_json))

    if site_json.get('add_content'):
        for it in site_json['add_content']:
            if it['position'] == 'top':
                contents = utils.get_soup_elements(it, soup)
                for el in contents:
                    item['content_html'] += wp_posts.format_content(el.decode_contents(), item, site_json, module_format_content)
                if it.get('separator'):
                    item['content_html'] += '<div>&nbsp;</div><hr style="width:80%; margin:auto;"/><div>&nbsp;</div>'

    if site_json.get('content'):
        contents = utils.get_soup_elements(site_json['content'], soup)
        for el in contents:
            item['content_html'] += wp_posts.format_content(el.decode_contents(), item, site_json, module_format_content)

    if site_json.get('add_content'):
        for it in site_json['add_content']:
            if it['position'] != 'top':
                contents = utils.get_soup_elements(it, soup)
                if contents and it.get('separator'):
                    item['content_html'] += '<div>&nbsp;</div><hr style="width:80%; margin:auto;"/><div>&nbsp;</div>'
                for el in contents:
                    item['content_html'] += wp_posts.format_content(el.decode_contents(), item, site_json, module_format_content)

    if gallery:
        item['content_html'] += '<h3>Gallery</h3>' + gallery

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
