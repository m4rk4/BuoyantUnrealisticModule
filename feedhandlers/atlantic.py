import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_video(video):
    captions = []
    if video.get('captionText'):
        captions.append(video['captionText'])
    if video.get('attributionText'):
        captions.append(video['attributionText'])
    caption = ' | '.join(captions)

    vid_src = ''
    for format in video['formats']:
        if format['encoding'] == 'H264':
            vid_src = format['url']
            break
    if not vid_src:
        logger.warning('unhandled video type')

    if video['vidWidth'] > video['vidHeight']:
        poster = get_img_src(video['horizontalPoster'])
    else:
        poster = get_img_src(video['verticalPoster'])
    return utils.add_video(vid_src, 'video/mp4', poster, caption)


def get_img_src(image, width=1000):
    img_src = ''
    if image.get('srcSet'):
        img_src = utils.image_from_srcset(image['srcSet'], width)
    if not img_src:
        if image.get('crop') and image['crop'].get('srcSet'):
            img_src = utils.image_from_srcset(image['crop']['srcSet'], width)
        if not img_src:
            img_src = image['url']
    return img_src

def add_image(image, orig_size=False):
    captions = []
    if image.get('captionText'):
        captions.append(image['captionText'])
    if image.get('attributionText'):
        captions.append(image['attributionText'])
    caption = ' | '.join(captions)

    if orig_size:
        return utils.add_image(image['url'], caption, width=image['width'], height=image['height'])

    img_src = get_img_src(image)
    return utils.add_image(img_src, caption)


def get_photo_content(url, args, site_json, save_debug=False):
    photo_html = utils.get_url_html(url)
    if not photo_html:
        return None

    soup = BeautifulSoup(photo_html, 'html.parser')
    for el in soup.find_all('script', type='application/ld+json'):
        ld_json = json.loads(el.string)
        if ld_json['@type'] == 'NewsArticle':
            break

    item = {}
    item['id'] = ld_json['mainEntityOfPage']['@id']
    item['url'] = ld_json['url']
    item['title'] = ld_json['headline']

    date = re.sub(r'(\+|-)(\d\d)(\d\d)$', r'\1\2:\3', ld_json['datePublished'])
    dt = datetime.fromisoformat(date).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    date = re.sub(r'(\+|-)(\d\d)(\d\d)$', r'\1\2:\3', ld_json['dateModified'])
    dt = datetime.fromisoformat(date).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for author in ld_json['author']:
        authors.append(author['name'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['_image'] = ld_json['image']

    el = soup.find('script', type='application/insights+json')
    if el:
        insights_json = json.loads(el.string)
        if insights_json.get('watson') and insights_json['watson'].get('keywords'):
            item['tags'] = insights_json['watson']['keywords'].copy()

    item['content_html'] = ''
    el = soup.find(id='article-content')
    if el:
        item['summary'] = el.p.get_text()
        item['content_html'] += el.decode_contents() + '<hr/>'

    for el in soup.find_all('li', class_='photo'):
        images = []
        for it in el.find_all('source'):
            image = {}
            m = re.search(r'/(\d+)x(\d+)/media', it['data-srcset'])
            if m:
                image['width'] = m.group(1)
                image['src'] = it['data-srcset']
                images.append(image)
        if not images:
            logger.warning('unknown image source in ' + url)
            continue
        image = utils.closest_dict(images, 'width', 1000)
        captions = []
        it = el.find(class_='caption')
        if it:
            captions.append(it.span.get_text().strip())
        it = el.find(class_='credit')
        if it:
            captions.append(it.get_text().strip())
        caption = ' | '.join(captions)
        item['content_html'] += utils.add_image(image['src'], caption) + '<br/>'
    return item

def get_content(url, args, site_json, save_debug=False):
    if '/photo/' in url:
        return get_photo_content(url, args, site_json, save_debug)

    article_html = utils.get_url_html(url)
    if not article_html:
        return None

    soup = BeautifulSoup(article_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None

    next_data = json.loads(el.string)
    #if save_debug:
    #    utils.write_file(next_data, './debug/debug.json')

    article_json = None
    for key, val in next_data['props']['pageProps']['urqlState'].items():
        data = json.loads(val['data'])
        if data.get('article') and data['article'].get('content'):
            article_json = data['article']

    if not article_json:
        logger.warning('unable to get article contents in ' + url)
        return None

    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['url']
    item['title'] = article_json['seoTitle']

    dt = datetime.fromisoformat(article_json['datePublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['dateModified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    for author in article_json['authors']:
        authors.append(author['displayName'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('primaryChannel'):
        tag = article_json['primaryChannel']['displayName']
        if not tag.casefold() in (it.casefold() for it in item['tags']):
            item['tags'].append(tag)
    if article_json.get('primaryCategory'):
        tag = article_json['primaryCategory']['displayName']
        if not tag.casefold() in (it.casefold() for it in item['tags']):
            item['tags'].append(tag)
    if article_json.get('categories'):
        for cat in article_json['categories']:
            tag = cat['slug'].replace('-', ' ')
            if not tag.casefold() in (it.casefold() for it in item['tags']):
                item['tags'].append(tag)
    if len(item['tags']) == 0:
        del item['tags']

    item['summary'] = article_json['shareText']

    content_html = ''
    if article_json.get('dek'):
        content_html += '<p><em>{}</em></p>'.format(article_json['dek'])

    if article_json.get('leadArt'):
        if re.search(r'LeadArtImage', article_json['leadArt']['__typename']):
            item['_image'] = article_json['leadArt']['image']['url']
            content_html += add_image(article_json['leadArt']['image'])
        elif article_json['leadArt']['__typename'] == 'Cinemagraph':
            item['_image'] = article_json['leadArt']['horizontalPoster']['url']
            content_html += add_video(article_json['leadArt'])
    else:
        item['_image'] = article_json['shareImageDefault']['url']

    is_floating = False
    for content in article_json['content']:
        if content['__typename'] == 'ArticleParagraphContent':
            if content['subtype'] == 'DROPCAP':
                soup = BeautifulSoup(content['innerHtml'], 'html.parser')
                for el in soup.find_all(class_='smallcaps'):
                    if el.string:
                        el.string = el.string.upper()
                    el.unwrap()
                inner_html = str(soup)
                if inner_html[0] == '“':
                    dropcap = inner_html[0:2]
                    inner_html = inner_html[2:]
                else:
                    dropcap = inner_html[0]
                    inner_html = inner_html[1:]
                content_html += '<p><span style="float:left; font-size:4em; line-height:0.8em;">{}</span>{}'.format(dropcap, inner_html)
                is_floating = True
            else:
                if content.get('subtype'):
                    logger.warning('unhandled ArticleParagraphContent subtype {} in {}'.format(content['subtype'], url))
                content_html += '<p>' + content['innerHtml']
            if is_floating:
                content_html += '<span style="clear:left;"></span>'
                is_floating = False
            content_html += '</p>'

        elif content['__typename'] == 'ArticleHeading':
            m = re.search('\d+$', content['headingSubtype'])
            content_html += '<h{0}>{1}</h{0}>'.format(m.group(0), content['innerHtml'])

        elif content['__typename'] == 'ArticlePullquote':
            content_html += utils.add_pullquote(content['innerHtml'])

        elif content['__typename'] == 'ArticleLegacyHtml':
            if content.get('innerHtml') and content['innerHtml'].startswith('<iframe'):
                soup = BeautifulSoup(content['innerHtml'], 'html.parser')
                if soup.iframe.get('src'):
                    content_html += utils.add_embed(soup.iframe['src'])
                elif soup.iframe.get('data-src'):
                    content_html += utils.add_embed(soup.iframe['data-src'])
            elif content['tagName'] == 'HR':
                content_html += '<hr/>'
            elif content['tagName'] == 'UL' or content['tagName'] == 'OL':
                content_html += '<{0}>{1}</{0}>'.format(content['tagName'].lower(), content['innerHtml'])
            elif content['tagName'] == 'DIV':
                content_html += '<div>{}</div>'.format(content['innerHtml'])
            elif content['tagName'] == 'P':
                if content.get('style'):
                    content_html += '<p style="{}">'.format(content['style'])
                else:
                    content_html += '<p>'
                content_html += content['innerHtml'] + '</p>'
            elif content['tagName'] == 'BLOCKQUOTE':
                content_html += utils.add_blockquote(content['innerHtml'])
            else:
                logger.debug('unhandled ArticleLegacyHtml tag {} in {}'.format(content['tagName'], url))

        elif re.search(r'InlineImage', content['__typename']):
            if content.get('alignment') and content['alignment'] == 'LEFT':
                content_html += '<div style="float:left; margin-right:8px;">' + add_image(content, True) + '</div>'
                is_floating = True
            else:
                content_html += add_image(content)

        elif re.search(r'ArticleRelatedContent', content['__typename']):
            pass

        else:
            logger.debug('unhandled content type {} in {}'.format(content['__typename'], url))

    item['content_html'] = content_html
    return item


def get_feed(url, args, site_json, save_debug=False):
    # All: https://www.theatlantic.com/feed/all/
    # Best of: https://www.theatlantic.com/feed/best-of/
    # Section: https://www.theatlantic.com/feed/channel/-----
    # Photos: http://feeds.feedburner.com/theatlantic/infocus
    return rss.get_feed(url, args, site_json, save_debug, get_content)
