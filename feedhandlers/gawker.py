import math, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss, youtube

import logging

logger = logging.getLogger(__name__)


def get_image_src(id, format, width=1000, height=''):
    size = ''
    if width:
        size = ',w_{}'.format(width)
    if height:
        size += ',h_{}'.format(height)
    if format == 'gif':
        return 'https://i.kinja-img.com/gawker-media/image/upload/c_scale,fl_progressive,q_80{}/{}.gif'.format(size, id)
    return 'https://i.kinja-img.com/gawker-media/image/upload/c_fill,f_auto,fl_progressive,g_center,pg_1,q_80{}/{}.{}'.format(size, id, format)


def add_image(image):
    if image['type'] == 'FullBleedWidget':
        img_src = get_image_src(image['image']['id'], image['image']['format'])
    else:
        img_src = get_image_src(image['id'], image['format'])
    captions = []
    if image.get('caption'):
        content = ''
        for it in image['caption']:
            content += render_content(it)
        if content:
            captions.append(content)
    if image.get('attribution'):
        if image['attribution'][0].get('label'):
            content = image['attribution'][0]['label'] + ': '
        else:
            content = ''
        for it in image['attribution'][0]['credit']:
            content += render_content(it)
        if content:
            captions.append(content)
    return utils.add_image(img_src, ' | '.join(captions))


def add_kinja_video(video):
    video_json = utils.get_url_json('https://kinja.com/api/core/video/views/videoById?videoId={}'.format(video['id']))
    if not video_json:
        logger.warning('unable to add Kinja video')
        return ''

    video_src = video_json['data']['fastlyUrl']

    if 'm3u8' in video_src:
        video_type = 'application/x-mpegURL'
    elif 'mp4' in video['contentUrl']:
        video_type = 'video/mp4'
    else:
        logger.warning('unknown video type in for '.format(video_src))
        video_type = 'application/x-mpegURL'

    poster = get_image_src(video_json['data']['poster']['id'], video_json['data']['poster']['format'])

    captions = []
    if video.get('caption'):
        content = ''
        for it in video['caption']:
            content += render_content(it)
        if content:
            captions.append(content)
    if video.get('attribution'):
        content = ''
        for it in video['attribution'][0]['credit']:
            content += render_content(it)
        if content:
            captions.append(content)
    if not captions:
        captions.append(video_json['data']['title'])

    return utils.add_video(video_src, video_type, poster, ' | '.join(captions))


def render_content(content):
    content_html = ''
    if content['type'] == 'Text':
        endtag = ''
        if 'Bold' in content['styles']:
            content_html += '<b>'
            endtag = '</b>' + endtag
        if 'Italic' in content['styles']:
            content_html += '<i>'
            endtag = '</i>' + endtag
        if 'Underline' in content['styles']:
            content_html += '<u>'
            endtag = '</u>' + endtag
        content_html += content['value'] + endtag

    elif content['type'] == 'Paragraph':
        value = ''
        for it in content['value']:
            value += render_content(it)
        if re.search(r'^\s*<b>(Read|Watch) more:?\s?</b>', value, flags=re.I):
            return ''
        if content.get('containers'):
            content_html += value
        else:
            content_html += '<p>{}</p>'.format(value)

    elif content['type'] == 'Header':
        value = ''
        for it in content['value']:
            value += render_content(it)
        if re.search(r'^Related:\s*<a\s', value, flags=re.I):
            return ''
        content_html += '<h{0}>{1}</h{0}>'.format(content['level'], value)

    elif content['type'] == 'LineBreak':
        content_html += '<br />'

    elif content['type'] == 'PageBreak' or content['type'] == 'HorizontalRule':
        content_html += '<hr style="width:80%;"/>'

    elif content['type'] == 'Link':
        content_html += '<a href="{}">'.format(content['reference'])
        for it in content['value']:
            content_html += render_content(it)
        content_html += '</a>'

    elif content['type'] == 'PullQuote':
        value = ''
        for it in content['value']:
            value += render_content(it)
        content_html += utils.add_pullquote(value)

    elif content['type'] == 'Quotable':
        quote = ''
        for it in content['content']:
            quote += render_content(it)
        cite = ''
        for it in content['attribution']:
            cite += render_content(it)
        if content.get('image'):
            img_src = get_image_src(content['image']['id'], content['image']['format'], 80, 80)
            poster = '{}/image?url={}&mask=circle'.format(config.server, quote_plus(img_src))
        content_html += '<div style="margin-top:1em; margin-bottom:1em;"><img style="float:left; margin-right:8px;" src="{}"/><div style="overflow:hidden;">{}<br/>&ndash;&nbsp;{}</div><div style="clear:left;"></div></div>'.format(poster, quote, cite)

    elif content['type'] == 'Image':
        content_html += add_image(content)

    elif content['type'] == 'FullBleedWidget':
        if content.get('image'):
            content_html += add_image(content)
        else:
            logger.warning('unhandled FullBleedWidget')

    elif content['type'] == 'KinjaVideo':
        content_html += add_kinja_video(content)

    elif content['type'] == 'YoutubeVideo':
        content_html += utils.add_embed('https://www.youtube.com/watch?v={}'.format(content['id']))

    elif content['type'] == 'YoutubePlaylist':
        content_html += utils.add_embed('https://www.youtube.com/watch?list={}&v={}'.format(content['id'], content['initialVideo']))

    elif content['type'] == 'Twitter':
        content_html += utils.add_embed(utils.get_twitter_url(content['id']))

    elif content['type'] == 'Instagram':
        content_html += utils.add_embed('https://www.instagram.com/p/' + content['id'])

    elif content['type'] == 'TikTok':
        content_html += utils.add_embed('https://www.tiktok.com/embed/v2/{}?lang=en-US'.format(content['id']))

    elif content['type'] == 'Iframe':
        if content['source'].startswith('https://platform.twitter.com/embed'):
            m = re.search(r'&id=(\d+)', content['source'])
            if m:
                content_html += utils.add_embed(utils.get_twitter_url(m.group(1)))
            else:
                content_html += utils.add_embed(content['source'])
        else:
            content_html += utils.add_embed(content['source'])

    elif content['type'] == 'ReviewBox':
        content_html += '<div style="width:90%; margin:auto; padding:8px; border:1px solid black; border-radius:10px;">'
        if content.get('editorsChoice'):
            content_html += '<div style="text-align:center;"><span style="color:white; background-color:red; padding:0.2em;">EDITOR\'S CHOICE</span></div>'
        content_html += '<div style="text-align:center;"><span style="font-size:1.2em;"><b>{}</b></span></div>'.format(content['title'])
        if content.get('stars'):
            content_html += '<div style="text-align:center;"><span style="font-size:1.5em; color:gold;">'
            stars = float(content['stars'])
            for i in range(math.floor(stars)):
                content_html += '&#9733;'
            if stars % 1:
                # The half-star unicde character (&#11240;) doesn't display with standard fonts
                content_html += '&#x00BD;'
            #for i in range(5 - math.ceil(stars)):
            #    content_html += '&#9734;'
            content_html += '</span></div>'
        if content.get('description'):
            content_html += '<p>{}</p>'.format(content['description'])
        if content.get('image'):
            content_html += utils.add_image(get_image_src(content['image']['id'], content['image']['format']))
        for text in content['text']:
            content_html += '<p><b>{}</b><br />{}</p>'.format(text['label'].upper(), text['value'])
        if content.get('cta') and content['cta'].get('reference'):
            content_html += '<div style="margin-top:0.5em; margin-bottom:0.5em; text-align:center;"><a href="{}"><span style="display:inline-block; min-width:8em; color:white; background-color:blue; padding:0.5em;">{}</span></a></div>'.format(utils.get_redirect_url(content['cta']['reference']), content['cta']['value'])
        content_html += '</div>'

    elif content['type'] == 'CommerceLink':
        content_html += '<p><a href="{}">{}</a></p>'.format(content['url'], content['text'])

    elif content['type'] == 'ContainerBreak':
        content_html += '<!-- ContainerBreak -->'

    elif re.search('CommerceInset|LinkPreview', content['type']):
        # Generally redundant
        pass

    else:
        logger.warning('unhandled content type ' + content['type'])

    if content.get('containers'):
        for container in reversed(content['containers']):
            if container['type'] == 'BlockQuote':
                content_html = utils.add_blockquote(content_html)
            elif container['type'] == 'List':
                #value = content_html.replace('<p>', '')
                #value = value.replace('</p>', '<br/><br/>')
                #if value.endswith('<br/><br/>'):
                #    value = value[:-10]
                value = re.sub(r'^<p>(.*)</p>$', r'\1', value)
                value = value.replace('</p><p>', '<br/><br/>')
                if container['style'] == 'Bullet':
                    content_html = '<ul><li>{}</li></ul>'.format(value)
                else:
                    content_html = '<ol><li>{}</li></ol>'.format(value)
            else:
                logger.warning('unhandled container type ' + container['type'])

    return content_html


def get_content(url, args, site_json, save_debug=False):
    item = {}
    split_url = urlsplit(url)
    m = re.search(r'-(\d+)$', split_url.path)
    if not m:
        logger.warning('unable to parse article id in {}'.format(url))
    api_url = 'https://{}/api/core/corepost/getList?id={}'.format(split_url.netloc, m.group(1))
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    article_json = api_json['data'][0]
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item['id'] = article_json['id']
    item['url'] = article_json['permalink']
    # Remove html tags
    item['title'] = BeautifulSoup(article_json['headline'], 'html.parser').get_text()

    tz = pytz.timezone(article_json['timezone'])
    dt = datetime.fromtimestamp(article_json['publishTimeMillis'] / 1000)
    dt_utc = tz.localize(dt).astimezone(pytz.utc)
    item['date_published'] = dt_utc.isoformat()
    item['_timestamp'] = dt_utc.timestamp()
    item['_display_date'] = utils.format_display_date(dt_utc)

    dt = datetime.fromtimestamp(article_json['lastUpdateTimeMillis'] / 1000)
    dt_utc = tz.localize(dt).astimezone(pytz.utc)
    item['date_modified'] = dt_utc.isoformat()

    if article_json.get('authorIds'):
        api_url = 'https://{}/api/profile/users?'.format(split_url.netloc)
        for author_id in article_json['authorIds']:
            api_url += 'ids={}&'.format(author_id)
        api_url = api_url[:-1]
        author_json = utils.get_url_json(api_url)
        if author_json:
            authors = []
            for author in author_json['data']:
                authors.append(author['displayName'])
            if authors:
                item['author'] = {}
                item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('tags'):
        item['tags'] = []
        for tag in article_json['tags']:
            item['tags'].append(tag['displayName'])

    if article_json.get('sharingMainImage'):
        item['_image'] = get_image_src(article_json['sharingMainImage']['id'], article_json['sharingMainImage']['format'], article_json['sharingMainImage']['width'])

    item['summary'] = article_json['plaintext']

    item['content_html'] = ''
    if article_json.get('subhead'):
        item['content_html'] += '<p><em>'
        for content in article_json['subhead']:
            item['content_html'] += render_content(content)
        item['content_html'] += '</em></p>'

    if article_json.get('featuredMedia'):
        item['content_html'] += render_content(article_json['featuredMedia'])

    if article_json.get('body'):
        for content in article_json['body']:
            item['content_html'] += render_content(content)

    item['content_html'] = re.sub(r'</(ol|ul)></blockquote><blockquote [^>]+><(ol|ul)>', '', item['content_html'])
    item['content_html'] = re.sub(r'</blockquote><blockquote [^>]+>', '<br/><br/>', item['content_html'])
    item['content_html'] = re.sub(r'</[ou]l><[ou]l>', '', item['content_html'])
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)


def test_handler():
    feeds = ['https://gizmodo.com/rss',
             'https://theinventory.com/rss']
    for url in feeds:
        get_feed({"url": url}, True)
