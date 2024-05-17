import random, re, string
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    # https://www.brightspot.com/documentation/brightspot-cms-developer-guide/latest/image-urls
    # Signature doesn't seem to matter
    sig = ''.join(random.choices(string.ascii_lowercase + string.digits, k=7))
    src = 'https://www.politico.com/dims4/default/{}/2147483647/resize/{}x/quality/80/?url='.format(sig, width)
    if img_src.startswith('https://static.politico.com/'):
        return src + quote_plus(img_src)
    elif img_src.startswith('https://www.politico.com/dims4'):
        query = parse_qs(urlsplit(img_src).query)
        if query.get('url'):
            return src + quote_plus(query['url'][0])
    return img_src


def get_content(url, args, site_json, save_debug=False):
    # https://www.politico.com/spring/cms-api/v1/live-updates/congress/2023_10_20
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('meta', attrs={"name": "brightspot.contentId"})
    if not el:
        logger.warning('unable to determine contentId in ' + url)
        return None

    # https://subscriber.politicopro.com/article/2014/02/api-serious-flaws-in-camps-tax-proposal-029269
    api_url = 'https://subscriber.politicopro.com/api/v1/page/article/' + el['content']
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    article_json = None
    for container in api_json['containers']:
        for slot in container['slots']:
            if slot.get('modules'):
                for module in slot['modules']:
                    if module['type'] == 'article':
                        article_json = module['data']

    if not article_json:
        logger.warning('unable to find article module in ' + url)
        return None

    item = {}
    item['id'] = article_json['content']['id']
    item['url'] = api_json['meta']['analyticsTags']['site_url']
    item['title'] = article_json['content']['title']

    dt = datetime.fromisoformat(article_json['content']['publishDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    authors = []
    for it in article_json['content']['contributors']:
        authors.append(it['fullName'])
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json['content'].get('topics'):
        item['tags'] = []
        for it in article_json['content']['topics']:
            item['tags'].append(it['label'])

    item['content_html'] = ''
    if article_json['content'].get('dek'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['content']['dek'])
        item['summary'] = article_json['content']['dek']
    elif article_json['content'].get('tease'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['content']['tease'])
        item['summary'] = article_json['content']['tease']

    if article_json['content'].get('media'):
        if article_json['content']['media']['type'] == 'video':
            item['_image'] = article_json['content']['media']['imageUrl']
            item['content_html'] += utils.add_video(article_json['content']['media']['url'], 'video/mp4', article_json['content']['media']['imageUrl'], article_json['content']['media']['title'])
        else:
            item['_image'] = article_json['content']['media']['url']
            captions = []
            if article_json['content']['media'].get('caption'):
                captions.append(article_json['content']['media']['caption'])
            if article_json['content']['media'].get('attribution'):
                captions.append(article_json['content']['media']['attribution'])
            item['content_html'] += utils.add_image(resize_image(item['_image']), ' | '.join(captions))

    # Content is truncated
    # for block in article_json['body']:
    #     if block['type'] == 'html' and block['contentTag'] == 'p':
    #         item['content_html'] += '<p>' + block['content'] + '</p>'
    #     elif block['type'] == 'ad':
    #         continue
    #     else:
    #         logger.warning('unhandled body block type {} in {}'.format(block['type'], item['url']))

    if article_json['content']['type'] == 'article':
        text = ''
        for el in soup.find_all('div', class_='container__column--story'):
            if el.find(class_=['container__column--story', 'below-story-text', 'media-item--story-lead', 'story-section']):
                continue
            it = el.find(class_='story-text')
            if it:
                text += it.decode_contents()
            else:
                text += el.decode_contents()
        story = BeautifulSoup(text, 'html.parser')
    elif article_json['content']['type'] == 'newsletterentry':
        story = soup.find('div', class_='story-text')
    elif article_json['content']['type'] == 'media' and article_json['content']['subtype'] == 'videotranscript':
        if not item['author'].get('name'):
            item['author']['name'] = 'POLITICO Video'
        it = soup.find('video', class_='video-js')
        if it:
            item['content_html'] += utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(it['data-account'], it['data-player'], it['data-video-id']))
        else:
            logger.warning('unable to find video content in ' + item['url'])
        return item
    elif article_json['content']['type'] == 'media' and article_json['content']['subtype'] == 'photogallery':
        el = soup.find(class_='subhead')
        if el:
            item['content_html'] += str(el)
        gallery = soup.find(class_='gallery-carousel')
        for el in gallery.find_all(class_='gallery-carousel-item'):
            it = el.find('img')
            if it:
                if it.get('data-lazy-img'):
                    img_src = it['data-lazy-img']
                else:
                    img_src = it['src']
                it = el.find('figcaption')
                if it:
                    caption = it.h2.decode_contents()
                else:
                    caption = ''
                item['content_html'] += utils.add_image(resize_image(img_src), caption) + '<div>&nbsp;</div>'
        return item

    for el in story.find_all(class_=['ad', 'pb-fam', 'shifty-wrapper', 'story-intro', 'story-meta', 'story-related', 'story-supplement', 'twitter-authors']):
        el.decompose()

    for el in story.find_all('style'):
        el.decompose()

    for el in story.find_all('a', href=re.compile(r'^/')):
        el['href'] = 'https://www.politico.com' + el['href']

    for el in story.find_all('p', class_='story-text__drop-cap'):
        new_html = re.sub(r'^(<[^>]*>)(\W?\w)', r'\1<span style="float:left; font-size:4em; line-height:0.8em;">\2</span>', str(el))
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in story.find_all('header', class_='block-p-header'):
        if el.h2:
            el.h2['style'] = 'background:#121522; color:#fff; text-transform:uppercase; padding:10px 20px; display:inline-block; width:100%; letter-spacing:2px;'
            el.unwrap()

    for el in story.find_all(class_='story-text__divider'):
        new_html = '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in story.find_all(class_=['story-enhancement', 'story-interrupt']):
        new_html = ''
        if el.find('figure', class_=['story-photo', 'type-photo']):
            it = el.find('img')
            if it:
                if it.get('data-lazy-img'):
                    img_src = it['data-lazy-img']
                else:
                    img_src = it['src']
                it = el.find('figcaption')
                if it:
                    caption = it.p.decode_contents()
                else:
                    caption = ''
                new_html = utils.add_image(resize_image(img_src), caption)
        elif el.find(class_='media-item__video'):
            it = el.find(class_='video-js')
            if it:
                new_html = utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(it['data-account'], it['data-player'], it['data-video-id']))
        elif el.find('iframe'):
            it = el.find('iframe')
            new_html = utils.add_embed(it['src'])
        elif el.find(class_='correction'):
            it = el.find(class_='correction')
            new_html = utils.add_blockquote(it.decode_contents())
        elif el.find('hr', class_='short-horizontal-rule'):
            new_html = '<hr style="border-top: 12px solid black; width: 13%; display: inline-block; margin-top: 20px;" />'
        elif el.find(class_='media-item__summary'):
            # This is generally a related article link
            el.decompose()
            continue
        elif el.find(id='weekend-promo'):
            el.decompose()
            continue
        elif el.find(class_=['inline-super-footer', 'related-narrative', 'story-tags']):
            el.decompose()
            continue
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled story-enhancement in ' + item['url'])
            #print(el.contents)

    if article_json['content']['type'] == 'newsletterentry':
        item['content_html'] = story.decode_contents()
    else:
        item['content_html'] += str(story)
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.politico.com/rss
  return rss.get_feed(url, args, site_json, save_debug, get_content)