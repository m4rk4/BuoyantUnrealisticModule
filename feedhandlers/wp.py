import html, json, pytz, re
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
    if paths[-1] == 'embed':
        args['embed'] = True
        del paths[-1]
        page_url = '{}://{}/{}'.format(split_url.scheme, split_url.netloc, '/'.join(paths))
    else:
        page_url = url
    base_url = '{}://{}'.format(split_url.scheme, split_url.netloc)

    page_html = utils.get_url_html(page_url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    if save_debug:
        utils.write_file(soup.prettify(), './debug/debug.html')

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

    page_json = None
    article_json = None
    for it in ld_json:
        if not it.get('@type'):
            continue
        if isinstance(it['@type'], str):
            if it['@type'] == 'WebPage':
                page_json = it
            elif not article_json and re.search(r'Article', it['@type']):
                article_json = it
            elif not article_json and it['@type'] == 'Product':
                if it.get('Review'):
                    article_json = it['Review']
        elif isinstance(it['@type'], list):
            if 'WebPage' in it['@type']:
                page_json = it
            elif not article_json and re.search(r'Article', '|'.join(it['@type'])):
                article_json = it
    if page_json and not article_json:
        article_json = page_json

    el = soup.find('link', attrs={"rel": "alternative", "type": "application/json+oembed"})
    if el:
        oembed_json = utils.get_url_json(el['href'])
    else:
        oembed_json = None

    item = {}

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
    if item.get('title') and re.search(r'#\d+', item['title']):
        item['title'] = html.unescape(item['title'])

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
            if '+' not in date:
                dt_loc = datetime.fromisoformat(date)
                tz_loc = pytz.timezone(site_json['timezone'])
                dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                date = dt.isoformat()
    if date:
        dt = datetime.fromisoformat(date.replace('Z', '+00:00')).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    date = ''
    if meta and meta.get('article:modified_time'):
        if isinstance(meta['article:modified_time'], list):
            date = meta['article:modified_time'][0]
        else:
            date = meta['article:modified_time']
    elif article_json and article_json.get('dateModified'):
        date = article_json['dateModified']
    if date:
        dt = datetime.fromisoformat(date.replace('Z', '+00:00')).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    if site_json.get('author'):
        for el in soup.find_all(site_json['author']['tag'], attrs=site_json['author']['attrs']):
            if el.name == 'a':
                authors.append(el.get_text())
            else:
                for it in el.find_all('a', href=re.compile(r'author')):
                    authors.append(it.get_text())
            if authors:
                break
    elif article_json and article_json.get('author'):
        if isinstance(article_json['author'], dict):
            if article_json['author'].get('name'):
                authors.append(article_json['author']['name'])
        elif isinstance(article_json['author'], list):
            for it in article_json['author']:
                if it.get('name'):
                    authors.append(it['name'])
    if not authors:
        if ld_json:
            for it in ld_json:
                if it.get('@type') and ((isinstance(it['@type'], str) and it['@type'] == 'Person') or (isinstance(it['@type'], list) and 'Person' in it['@type'])):
                    authors.append(it['name'])
        if meta and meta.get('author'):
            authors.append(meta['author'])
        elif meta and meta.get('citation_author'):
            authors.append(meta['citation_author'])
        elif meta and meta.get('parsely-author'):
            authors.append(meta['parsely-author'])
        elif oembed_json and oembed_json.get('author_name'):
            authors.append(oembed_json['author_name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif site_json.get('authors'):
        item['author'] = {"name": site_json['authors']['default']}

    item['tags'] = []
    if site_json.get('tags'):
        for el in soup.find_all(site_json['tags']['tag'], attrs=site_json['tags']['attrs']):
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
        item['tags'] = meta['article:tag'].copy()
    elif meta and meta.get('parsely-tags'):
        item['tags'] = list(map(str.strip, meta['parsely-tags'].split(',')))
    elif meta and meta.get('keywords'):
        item['tags'] = list(map(str.strip, meta['keywords'].split(',')))
    if not item.get('tags'):
        del item['tags']

    if ld_json:
        for it in ld_json:
            if it.get('@type') and it['@type'] == 'ImageObject':
                item['_image'] = it['url']
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
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;"><a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a><div style="margin-left:8px; margin-right:8px;"><h4><a href="{}">{}</a></h4><p><small>{}</small></p></div></div>'.format(item['url'], item['_image'], item['url'], item['title'], item['summary'])
        return item

    item['content_html'] = ''
    if 'add_subtitle' in args:
        if site_json.get('subtitle'):
            el = soup.find(site_json['subtitle']['tag'], attrs=site_json['subtitle']['attrs'])
            if el:
                item['content_html'] += '<p><em>{}</em></p>'.format(el.get_text())
        elif item.get('summary'):
            item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    if 'add_lede_img' in args:
        if 'no_lede_caption' in args:
            add_caption = False
        else:
            add_caption = True
        lede = False
        if site_json.get('lede_video'):
            el = soup.find(site_json['lede_video']['tag'], attrs=site_json['lede_video']['attrs'])
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
        if not lede and site_json.get('lede_img'):
            el = soup.find(site_json['lede_img']['tag'], attrs=site_json['lede_img']['attrs'])
            if el:
                if el.find('img'):
                    item['content_html'] += wp_posts.add_image(el, None, base_url, add_caption)
                    lede = True
                else:
                    it = el.find('iframe')
                    if it:
                        item['content_html'] += utils.add_embed(it['src'])
                        lede = True
        if not lede:
            item['content_html'] += utils.add_image(wp_posts.resize_image(item['_image']))

    if site_json.get('content'):
        for el in soup.find_all(site_json['content']['tag'], attrs=site_json['content']['attrs']):
            if site_json.get('decompose'):
                for tag in site_json['decompose']:
                    for it in el.find_all(tag['tag'], attrs=tag['attrs']):
                        it.decompose()
            it = el.find('body')
            if it:
                item['content_html'] += wp_posts.format_content(it.decode_contents(), item, site_json, module_format_content)
            else:
                item['content_html'] += wp_posts.format_content(el.decode_contents(), item, site_json, module_format_content)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
