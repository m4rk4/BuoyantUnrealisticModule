import base64, copy, itertools, json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wirecutter

import logging

logger = logging.getLogger(__name__)


def format_text(block):
    start_tags = []
    end_tags = []
    if 'formats' in block:
        for fmt in block['formats']:
            if fmt['__typename'] == 'LinkFormat':
                start_tags.append('<a href="{}">'.format(fmt['url']))
                end_tags.insert(0, '</a>')
            elif fmt['__typename'] == 'BoldFormat':
                start_tags.append('<b>')
                end_tags.insert(0, '</b>')
            elif fmt['__typename'] == 'ItalicFormat':
                start_tags.append('<i>')
                end_tags.insert(0, '</i>')
            else:
                logger.warning('Unhandled format type ' + fmt['__typename'])

    text_html = ''.join(start_tags)
    if 'text' in block:
        text_html += block['text']
    elif 'text@stripHtml' in block:
        text_html += block['text@stripHtml']
    else:
        logger.warning('no text in ' + block['__typename'])
    text_html += ''.join(end_tags)
    return text_html


def render_block(block, arg1=None, arg2=None):
    full_header = False
    block_html = ''
    if block['__typename'] == 'Dropzone' or block['__typename'] == 'EmailSignupBlock':
        pass

    elif block['__typename'] == 'TextInline':
        block_html += format_text(block)

    elif block['__typename'] == 'TextOnlyDocumentBlock':
        block_html += block['text']

    elif block['__typename'] == 'ParagraphBlock':
        block_html += '<p>'
        for blk in block['content']:
            block_html += render_block(blk)
        block_html += '</p>'

    elif block['__typename'] == 'CapsuleBlock':
        block_html += render_block(block['capsuleContent'])

    elif block['__typename'] == 'Capsule':
        block_html += render_block(block['body'])

    elif block['__typename'] == 'DocumentBlock':
        for blk in block['content']:
            block_html += render_block(blk)

    elif block['__typename'] == 'ListBlock':
        if block['style'] == 'UNORDERED':
            block_tag = 'ul'
        else:
            block_tag = 'ol'
        block_html += '<{}>'.format(block_tag)
        for blk in block['content']:
            block_html += render_block(blk)
        block_html += '</{}>'.format(block_tag)

    elif block['__typename'] == 'ListItemBlock':
        block_html += '<li>'
        for blk in block['content']:
            block_html += render_block(blk)
        block_html += '</li>'

    elif block['__typename'] == 'HeaderBasicBlock' or block['__typename'] == 'HeaderFullBleedHorizontalBlock'  or block['__typename'] == 'HeaderFullBleedVerticalBlock' or block['__typename'] == 'HeaderMultimediaBlock':
        if full_header:
            if block.get('headline'):
                block_html += render_block(block['headline'])
            if block.get('timestampBlock'):
                block_html += render_block(block['timestampBlock'])
        if block.get('byline'):
            block_html += render_block(block['byline'])
        if block.get('summary'):
            block_html += render_block(block['summary'])
        if block.get('ledeMedia'):
            block_html += render_block(block['ledeMedia'])
        if block.get('media'):
            block_html += render_block(block['media'])

    elif re.search(r'Heading\dBlock', block['__typename']):
        m = re.search(r'Heading(\d)Block', block['__typename'])
        block_html += '<h{}>'.format(m.group(1))
        for blk in block['content']:
            block_html += render_block(blk)
        block_html += '</h{}>'.format(m.group(1))

    elif block['__typename'] == 'DetailBlock' or block['__typename'] == 'SummaryBlock':
        block_html += '<p><em>'
        for blk in block['content']:
            block_html += render_block(blk)
        block_html += '</em></p>'

    elif block['__typename'] == 'BylineBlock':
        if full_header:
            block_html += '<p><strong>'
            for blk in block['bylines']:
                block_html += render_block(blk)
            block_html += '</strong>'
            if block.get('role'):
                block_html += '<br/><em>About the author: '
                for blk in block['role']:
                    block_html += render_block(blk)
            block_html += '</em></p>'
        else:
            if block.get('role'):
                block_html += '<p><em>About the author: '
                for blk in block['role']:
                    block_html += render_block(blk)
                block_html += '</em></p>'

    elif block['__typename'] == 'Byline':
        block_html += block['prefix'] + ' '
        creators = []
        for it in block['creators']:
            creators.append(it['displayName'])
        block_html += re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(creators))

    elif block['__typename'] == 'TimestampBlock':
        dt = datetime.fromisoformat(block['timestamp'].replace('Z', '+00:00'))
        block_html += '<p>' + utils.format_display_date(dt) + '</p>'

    elif block['__typename'] == 'BlockquoteBlock':
        quote = ''
        for blk in block['content']:
            quote += render_block(blk)
        block_html += utils.add_blockquote(quote)

    elif block['__typename'] == 'ImageBlock':
        block_html += render_block(block['media'])

    elif block['__typename'] == 'DiptychBlock':
        for key, blk in block.items():
            if key.startswith('image'):
                block_html += render_block(blk)
            elif key not in ['__typename', 'size']:
                logger.warning('unhandled DiptychBlock key ' + key)

    elif block['__typename'] == 'Image':
        images = []
        for it in block['crops']:
            images += it['renditions']
        image = utils.closest_dict(images, 'width', 1000)
        captions = []
        if block.get('caption'):
            it = render_block(block['caption']).strip()
            if it:
                captions.append(it)
        if block.get('credit'):
            captions.append(block['credit'])
        block_html += utils.add_image(image['url'], ' | '.join(captions))

    elif block['__typename'] == 'VideoBlock':
        block_html += render_block(block['media'])

    elif block['__typename'] == 'Video':
        for it in block['renditions']:
            if it['type'] == 'video_480p_mp4':
                video = it
                break
        for it in block['promotionalMedia']['crops']:
            if it['name'] == 'MASTER':
                image = utils.closest_dict(it['renditions'], 'width', 1000)
        caption = block['summary'] + ' | ' + block['promotionalMedia']['credit']
        block_html += utils.add_video(video['url'], 'video/mp4', image['url'], caption)

    elif block['__typename'] == 'AudioBlock':
        block_html += render_block(block['media'])

    elif block['__typename'] == 'Audio':
        image = block['promotionalMedia']['crops'][0]['renditions'][0]
        poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(image['url']))
        block_html += '<table><tr><td><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><a href="{}"><strong>{}</strong></a><br/>{}<br/><a href="https://www.nytimes.com/column/{}"><small>{}</small></a></td></tr></table>'.format(block['fileUrl'], poster, block['fileUrl'], block['headline']['default'], block['summary'], block['podcastSeries']['name'], block['podcastSeries']['title'])

    elif block['__typename'] == 'InteractiveBlock':
        block_html += render_block(block['media'])

    elif block['__typename'] == 'Interactive':
        for it in block['promotionalMedia']['spanImageCrops']:
            if it['name'] == 'MASTER':
                image = utils.closest_dict(it['renditions'], 'width', 400)
        block_html += '<table><tr><td><a href="{}"><img src="{}" width="160px"/></a></td><td style="vertical-align:top;"><a href="{}"><strong>{}</strong></a><br/>{}</td></tr></table>'.format(block['url'], image['url'], block['url'], block['headline']['default'], block['summary'])

    elif block['__typename'] == 'EmbeddedInteractive':
        if block['appName'] == 'Datawrapper':
            soup = BeautifulSoup(block['html'], 'html.parser')
            it = soup.find('iframe')
            if it:
                block_html += utils.add_embed(it['src'])
            else:
                logger.warning('unhandled Datawrapper embed')
        elif block['appName']:
            logger.warning('unhandled EmbeddedInteractive ' + block['appName'])
        else:
            embed_html = '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>{}</body></html>'.format(block['html'])
            embed_b64 = base64.b64encode(embed_html.encode('utf-8'))
            block_html += '<h4><a href="data:text/html;base64,{}">View embedded content</a></h4>'.format(embed_b64.decode('utf-8'))

    elif block['__typename'] == 'YouTubeEmbedBlock':
        block_html += utils.add_embed('https://www.youtube.com/embed/' + block['youTubeId'])

    elif block['__typename'] == 'TwitterEmbedBlock':
        block_html += utils.add_embed(block['twitterUrl'])

    elif block['__typename'] == 'InstagramEmbedBlock':
        block_html += utils.add_embed(block['instagramUrl'])

    elif block['__typename'] == 'RuleBlock':
        block_html += '<hr/>'

    elif block['__typename'] == 'LineBreakInline':
        block_html += '<br/>'

    elif block['__typename'] == 'RelatedLinksBlock':
        block_html += '<h3>'
        for blk in block['title']:
            block_html += render_block(blk)
        block_html += '</h3><ul>'
        for it in block['related']:
            block_html += '<li><a href="{}">{}</a></li>'.format(it['url'], it['headline']['default'])
        block_html += '</ul>'


    else:
        logger.warning('unhandled content block ' + block['__typename'])

    return block_html


def get_video_json(video_id, save_debug):
    # From: https://static01.nyt.com/video-static/vhs3/vhs.min.js
    data = {"query": "\nquery VideoQuery($id: String!) {\n  video(id: $id) {\n    ...on Video {\n      __typename\n      id\n      bylines {\n        renderedRepresentation\n      }\n      contentSeries\n      cues {\n        name\n        type\n        timeIn\n        timeOut\n      }\n      duration\n      embedded\n      headline {\n        default\n      }\n      firstPublished\n      lastModified\n      is360\n      isLive\n      liveUrls\n      playlist {\n        headline {\n          default\n        }\n        promotionalHeadline\n        url\n        sourceId\n        section {\n          displayName\n        }\n        videos(first: 10) {\n          edges @filterEmpty {\n            node {\n              id\n              sourceId\n              duration\n              section {\n                id\n                name\n              }\n              headline {\n                default\n              }\n              renditions {\n                url\n                type\n              }\n              url\n              promotionalMedia {\n                ... on Image {\n                  crops(cropNames: [SMALL_SQUARE, MEDIUM_SQUARE, SIXTEEN_BY_NINE]) {\n                    renditions {\n                      name\n                      width\n                      height\n                      url\n                    }\n                  }\n                }\n              }\n            }\n          }\n        }\n      }\n      promotionalHeadline\n      promotionalMedia {\n        ... on Image {\n          crops (cropNames: [SMALL_SQUARE, MEDIUM_SQUARE, SIXTEEN_BY_NINE, THREE_BY_TWO, TWO_BY_THREE, FLEXIBLE]) {\n            name\n            renditions {\n              name\n              width\n              height\n              url\n            }\n          }\n        }\n      }\n      promotionalSummary\n      renditions {\n        type\n        width\n        height\n        url\n        bitrate\n      }\n      section {\n        name\n      }\n      shortUrl\n      sourceId\n      subsection {\n        name\n      }\n      summary\n      timesTags {\n        __typename\n        displayName\n        isAdvertisingBrandSensitive\n        vernacular\n      }\n      uri\n      url\n    }\n  }\n}",
                 "variables": {"id": video_id}
        }
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "content-type": "application/json",
        "nyt-app-type": "vhs",
        "nyt-app-version": "v3.52.2",
        "nyt-token": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuNIzKBOFB77aT/jN/FQ+/QVKWq5V1ka1AYmCR9hstz1pGNPH5ajOU9gAqta0T89iPnhjwla+3oec/Z3kGjxbpv6miQXufHFq3u2RC6HyU458cLat5kVPSOQCe3VVB5NRpOlRuwKHqn0txfxnwSSj8mqzstR997d3gKB//RO9zE16y3PoWlDQXkASngNJEWvL19iob/xwAkfEWCjyRILWFY0JYX3AvLMSbq7wsqOCE5srJpo7rRU32zsByhsp1D5W9OYqqwDmflsgCEQy2vqTsJjrJohuNg+urMXNNZ7Y3naMoqttsGDrWVxtPBafKMI8pM2ReNZBbGQsQXRzQNo7+QIDAQAB",
        "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }
    gql_json = utils.post_url('https://samizdat-graphql.nytimes.com/graphql/v2', json_data=data, headers=headers)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/video.json')
    return gql_json['data']['video']


def get_content(url, args, save_debug=False):
    if re.search('/(live|interactive)/', url):
        logger.warning('unsupported url ' + url)
        return None

    article_html = utils.get_url_html(url, user_agent='googlebot')
    if not article_html:
        return None
    if save_debug:
        utils.write_file(article_html, './debug/debug.html')

    soup = BeautifulSoup(article_html, 'html.parser')

    article_json = None
    if '/video/' in url:
        el = soup.find('meta', attrs={"name": "nyt_uri"})
        if el:
            article_json = get_video_json(el['content'], save_debug)
    else:
        preloaded_data = ''
        el = soup.find('script', string=re.compile(r'window\.__preloadedData'))
        if el:
            preloaded_data = el.string[25:-1]
        else:
            m = re.search(r'<script>window\.__preloadedData = (.+);</script>', article_html)
            if m:
                preloaded_data = m.group(1)
        if not preloaded_data:
            logger.warning('No preloadData found in ' + url)
            return None
        if save_debug:
            utils.write_file(preloaded_data, './debug/debug.txt')

        try:
            preloaded_json = json.loads(preloaded_data.replace(':undefined', ':""'))
        except:
            logger.warning('unable to convert preloadedData to json in ' + url)
            return None
        if save_debug:
            utils.write_file(preloaded_data, './debug/data.json')

        article_json = preloaded_json['initialData']['data']['article']

    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['url']
    item['title'] = article_json['headline']['default']

    dt = datetime.fromisoformat(article_json['firstPublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['lastModified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('bylines'):
        item['author']['name'] = re.sub(r'^By ', '', article_json['bylines'][0]['renderedRepresentation'])
    else:
        item['author'] = article_json['desk']

    if article_json.get('timesTags'):
        item['tags'] = []
        for it in article_json['timesTags']:
            item['tags'].append(it['displayName'])

    item['summary'] = article_json['summary']

    item['content_html'] = ''
    if article_json['__typename'] == 'Video':
        for it in article_json['renditions']:
            if it['type'] == 'video_480p_mp4':
                item['_video'] = it['url']
                break
        for it in article_json['promotionalMedia']['crops']:
            if it['name'] == 'SIXTEEN_BY_NINE':
                item['_image'] = utils.closest_dict(it['renditions'], 'width', 1000)['url']
        item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'])
        item['content_html'] += '<p>' + article_json['summary'] + '</p>'

    else:
        if article_json.get('promotionalMedia'):
            if article_json['promotionalMedia']['__typename'] == 'Image':
                crops = article_json['promotionalMedia']['assetCrops']
            else:
                crops = article_json['promotionalMedia']['promotionalMedia']['assetCrops']
            for it in crops:
                if it['name'] == 'MASTER':
                    image = utils.closest_dict(it['renditions'], 'width', 1500)
                    item['_image'] = image['url']
                    break
        for block in article_json['sprinkledBody']['content']:
            item['content_html'] += render_block(block)

    item['content_html'] = re.sub(r'</figure><(figure|table)', r'</figure><br/><\1', item['content_html'])
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
