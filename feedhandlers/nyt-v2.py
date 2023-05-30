import base64, json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote_plus, urlsplit

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


def render_block(block, full_header=False, headline_url=''):
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
            block_html += render_block(blk, full_header, headline_url)

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
                if headline_url:
                    block_html += '<a href="{}">{}</a>'.format(headline_url, render_block(block['headline']))
                else:
                    block_html += render_block(block['headline'])
            if block.get('timestampBlock'):
                block_html += render_block(block['timestampBlock'])
        if block.get('byline'):
            block_html += render_block(block['byline'], full_header)
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
                block_html += '<br/><em><small>About the author: '
                for blk in block['role']:
                    block_html += render_block(blk)
            block_html += '</small></em></p>'
        else:
            if block.get('role'):
                block_html += '<p><em><small>About the author: '
                for blk in block['role']:
                    block_html += render_block(blk)
                block_html += '</small></em></p>'

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

    elif block['__typename'] == 'UnstructuredBlock':
        if block.get('mediaRefs'):
            for blk in block['mediaRefs']:
                block_html += render_block(blk)
        elif block['dataType'] == 'ExperimentalBlock_DocPromo':
            data_json = json.loads(block['data'])
            block_html += utils.add_blockquote('<a href="https://www.nytimes.com/{}"><b>{}</b></a><br/>{}'.format(data_json['documentData']['publishPath'], data_json['documentData']['name'], data_json['documentData']['description']))
        else:
            logger.warning('unhandled UnstructuredBlock')

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
            if re.search(r'video_480p_mp4', it['type']):
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
        if block.get('promotionalMedia'):
            image = block['promotionalMedia']['crops'][0]['renditions'][0]
            poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(image['url']))
        else:
            poster = '{}/image?width=64&height=64&overlay=audio'.format(config.server)
        block_html += '<table><tr><td><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><a href="{}"><strong>{}</strong></a><br/>{}'.format(block['fileUrl'], poster, block['fileUrl'], block['headline']['default'], block['summary'])
        if block.get('podcastSeries'):
            block_html += '<br/><a href="https://www.nytimes.com/column/{}"><small>{}</small></a>'.format(block['podcastSeries']['name'], block['podcastSeries']['title'])
        block_html += '</td></tr></table>'

    elif block['__typename'] == 'GridBlock':
        block_html += '<div><strong>{}</strong><br/>'.format(block['caption'])
        for blk in block['gridMedia']:
            block_html += render_block(blk)
        block_html += '</div>'

    elif block['__typename'] == 'InteractiveBlock':
        block_html += render_block(block['media'])

    elif block['__typename'] == 'Interactive':
        for it in block['promotionalMedia']['spanImageCrops']:
            if it['name'] == 'MASTER':
                image = utils.closest_dict(it['renditions'], 'width', 400)
        block_html += '<table><tr><td><a href="{}"><img src="{}" width="160px"/></a></td><td style="vertical-align:top;"><a href="{}"><strong>{}</strong></a><br/>{}</td></tr></table>'.format(block['url'], image['url'], block['url'], block['headline']['default'], block['summary'])

    elif block['__typename'] == 'EmbeddedInteractive':
        soup = BeautifulSoup(block['html'], 'html.parser')
        if block['appName'] == 'Datawrapper':
            it = soup.find('iframe')
            if it:
                block_html += utils.add_embed(it['src'])
            else:
                logger.warning('unhandled Datawrapper embed')
        elif block['appName'] == 'Pilot':
            m = re.search(r'window\.bursts\.state\[\'[^\']+\'\] = "([^"]+)"', block['html'])
            if m:
                burst_json = json.loads(unquote_plus(m.group(1)))
                block_html += '<hr/>'
                for blk in burst_json['title']['content']:
                    block_html += render_block(blk)
                for it in burst_json['items']:
                    for blk in it['body']['content']:
                        block_html += render_block(blk)
                block_html += '<hr/>'
            else:
                logger.warning('unhandled card in Pilot EmbeddedInteractive')
        elif soup.find('blockquote', class_='tiktok-embed'):
            block_html += utils.add_embed(soup.blockquote['cite'])
        elif block.get('slug') and 'burst-video' in block['slug']:
            #video_json = get_video_json(block['uri'], True)
            logger.warning('unhandled burst-video')
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

    elif block['__typename'] == 'LabelBlock':
        block_html += '<h4>'
        for blk in block['content']:
            block_html += render_block(blk)
        block_html += '</h4>'

    elif block['__typename'] == 'RuleBlock':
        block_html += '<hr/>'

    elif block['__typename'] == 'LineBreakInline':
        block_html += '<br/>'

    elif block['__typename'] == 'RelatedLinksBlock':
        if block.get('title'):
            block_html += '<h3 style="margin-bottom:0;">'
            for blk in block['title']:
                block_html += render_block(blk)
            block_html += '</h3>'
        if block.get('description'):
            block_html += '<p style="font-style:italic; margin-top:0;">'
            for blk in block['description']:
                block_html += render_block(blk)
            block_html += '</p>'

        if block.get('related'):
            block_html += '<ul style="margin-top:0;">'
            for it in block['related']:
                block_html += '<li><a href="{}">{}</a></li>'.format(it['url'], it['headline']['default'])
            block_html += '</ul>'

    else:
        logger.warning('unhandled content block ' + block['__typename'])

    return block_html


def get_video_json(video_id, save_debug):
    # From: https://static01.nyt.com/video-static/vhs3/vhs.min.js
    data = {
        "query": "\nquery VideoQuery($id: String!) {\n  video(id: $id) {\n    ...on Video {\n      __typename\n      id\n      bylines {\n        renderedRepresentation\n      }\n      contentSeries\n      cues {\n        name\n        type\n        timeIn\n        timeOut\n      }\n      duration\n      embedded\n      headline {\n        default\n      }\n      firstPublished\n      lastModified\n      is360\n      isLive\n      liveUrls\n      playlist {\n        headline {\n          default\n        }\n        promotionalHeadline\n        url\n        sourceId\n        section {\n          displayName\n        }\n        videos(first: 10) {\n          edges @filterEmpty {\n            node {\n              id\n              sourceId\n              duration\n              section {\n                id\n                name\n              }\n              headline {\n                default\n              }\n              renditions {\n                url\n                type\n              }\n              url\n              promotionalMedia {\n                ... on Image {\n                  crops(cropNames: [SMALL_SQUARE, MEDIUM_SQUARE, SIXTEEN_BY_NINE]) {\n                    renditions {\n                      name\n                      width\n                      height\n                      url\n                    }\n                  }\n                }\n              }\n            }\n          }\n        }\n      }\n      promotionalHeadline\n      promotionalMedia {\n        ... on Image {\n          crops (cropNames: [SMALL_SQUARE, MEDIUM_SQUARE, SIXTEEN_BY_NINE, THREE_BY_TWO, TWO_BY_THREE, FLEXIBLE]) {\n            name\n            renditions {\n              name\n              width\n              height\n              url\n            }\n          }\n        }\n      }\n      promotionalSummary\n      renditions {\n        type\n        width\n        height\n        url\n        bitrate\n      }\n      section {\n        name\n      }\n      shortUrl\n      sourceId\n      subsection {\n        name\n      }\n      summary\n      timesTags {\n        __typename\n        displayName\n        isAdvertisingBrandSensitive\n        vernacular\n      }\n      uri\n      url\n    }\n  }\n}",
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


def get_content(url, args, site_json, save_debug=False):
    if re.search('/(live|interactive)/', url):
        logger.warning('unsupported url ' + url)
        return None
    elif '/wirecutter/' in url:
        return wirecutter.get_content(url, args, site_json, save_debug)

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
            utils.write_file(preloaded_json, './debug/data.json')

        if '/explain/' in url:
            article_json = preloaded_json['initialData']['data']['explainerAsset']
        else:
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
    elif article_json.get('desk'):
        item['author']['name'] = article_json['desk']
    elif '/explain/' in item['url']:
        item['author']['name'] = 'The New York Times Explainer'
    else:
        item['author']['name'] = 'The New York Times'

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

        if article_json.get('groupings'):
            for group in article_json['groupings']:
                container = next((it for it in group['containers'] if it['name'] == 'feed lede'), None)
            if container:
                for it in container['relations']:
                    item['content_html'] += render_block(it['asset']['body'], True)

        if article_json.get('highlights'):
            item['content_html'] += '<h3>Contents:</h3><ul>'
            for it in article_json['highlights']['edges']:
                item['content_html'] += '<li>{}</li>'.format(it['node']['headline']['default'])
            item['content_html'] += '</ul>'
            for it in article_json['highlights']['edges']:
                item['content_html'] += '<hr/>'
                if it['node']['__typename'] == 'Article':
                    if item['url'] in it['node']['url']:
                        item['content_html'] += render_block(it['node']['body'], True)
                    else:
                        item['content_html'] += render_block(it['node']['body'], True, it['node']['url'])
                else:
                    logger.warning('skipping highlight type {} in {}'.format(it['node']['__typename'], item['url']))

        if article_json.get('sprinkledBody'):
            item['content_html'] += render_block(article_json['sprinkledBody'])

    item['content_html'] = re.sub(r'</figure><(figure|table)', r'</figure><br/><\1', item['content_html'])
    return item


def get_collection(path):
    data = {
        "operationName": "CollectionsQuery",
        "variables": {
            "id": path,
            "first": 10,
            "streamQuery": {
                "sort": "newest"
            },
            "exclusionMode": "HIGHLIGHTS_AND_EMBEDDED",
            "isHighEnd": False,
            "highlightsListUri": "nyt://per/personalized-list/__null__",
            "highlightsListFirst": 0,
            "hasHighlightsList": False,
            "cursor": "YXJyYXljb25uZWN0aW9uOjA="
        },
        "extensions": {
            "persistedQuery": {
                "version": 1, "sha256Hash": "5bf74f1861a95e95479325803a93c290404da1a1b61929256077b42f290e0a05"
            }
        }
    }
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "content-type": "application/json",
        "nyt-app-type": "project-vi",
        "nyt-app-version": "0.0.5",
        "nyt-token": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAs+/oUCTBmD/cLdmcecrnBMHiU/pxQCn2DDyaPKUOXxi4p0uUSZQzsuq1pJ1m5z1i0YGPd1U1OeGHAChWtqoxC7bFMCXcwnE1oyui9G1uobgpm1GdhtwkR7ta7akVTcsF8zxiXx7DNXIPd2nIJFH83rmkZueKrC4JVaNzjvD+Z03piLn5bHWU6+w+rA+kyJtGgZNTXKyPh6EC6o5N+rknNMG5+CdTq35p8f99WjFawSvYgP9V64kgckbTbtdJ6YhVP58TnuYgr12urtwnIqWP9KSJ1e5vmgf3tunMqWNm6+AnsqNj8mCLdCuc5cEB74CwUeQcP2HQQmbCddBy2y0mEwIDAQAB",
        "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"112\", \"Chromium\";v=\"112\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }
    gql_json = utils.post_url('https://samizdat-graphql.nytimes.com/graphql/v2', json_data=data, headers=headers)
    if not gql_json:
        return None
    return gql_json


def get_live_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    dt = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(pytz.timezone('US/Eastern'))
    paths[1] = dt.strftime('%Y')
    paths[2] = dt.strftime('%m')
    paths[3] = dt.strftime('%d')
    path = '/' + '/'.join(paths)
    url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, path)
    print(path)
    data = {
        "operationName": "LiveBlogQuery",
        "variables": {
            "collectionUrl": path,
            "previewUris":[],
            "blogItemSocialPostId": "nyt://",
            "reporterUpdateSocialPostId": "nyt://",
            "first": 15,
            "additionalFirst": 38,
            "id": url,
            "after": "YXJyYXljb25uZWN0aW9uOjE0",
            "before": "",
            "last": "",
            "additionalAfter": "YXJyYXljb25uZWN0aW9uOjEw",
            "additionalBefore": "",
            "additionalLast": ""
        },
        "extensions": {"persistedQuery": {            "version":1,"sha256Hash":"a4f3f780bebcd7ea613dfe4fd44c06639f371f7bab3c5f4efd15741e205c0193"
            }
        }
    }
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "content-type": "application/json",
        "nyt-app-type": "project-vi",
        "nyt-app-version": "0.0.5",
        "nyt-token": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAs+/oUCTBmD/cLdmcecrnBMHiU/pxQCn2DDyaPKUOXxi4p0uUSZQzsuq1pJ1m5z1i0YGPd1U1OeGHAChWtqoxC7bFMCXcwnE1oyui9G1uobgpm1GdhtwkR7ta7akVTcsF8zxiXx7DNXIPd2nIJFH83rmkZueKrC4JVaNzjvD+Z03piLn5bHWU6+w+rA+kyJtGgZNTXKyPh6EC6o5N+rknNMG5+CdTq35p8f99WjFawSvYgP9V64kgckbTbtdJ6YhVP58TnuYgr12urtwnIqWP9KSJ1e5vmgf3tunMqWNm6+AnsqNj8mCLdCuc5cEB74CwUeQcP2HQQmbCddBy2y0mEwIDAQAB",
        "sec-ch-ua": "\".Not/A)Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }
    gql_json = utils.post_url('https://samizdat-graphql.nytimes.com/graphql/v2', data=json.dumps(data), headers=headers)
    if not gql_json:
        return None
    return gql_json


def get_feed(url, args, site_json, save_debug=False):
    feed = None
    if args['url'].endswith('.xml') or args['url'].endswith('/feed/'):
        feed = rss.get_feed(url, args, site_json, save_debug, get_content)
        m = re.search(r'publish/https://www\.nytimes\.com/(.*)/rss\.xml', args['url'])
        if m:
            collection = get_collection(m.group(1))
            if collection:
                if save_debug:
                    utils.write_file(collection, './debug/feed.json')
                highlights = collection['data']['legacyCollection']['highlights']['edges']
                streams = collection['data']['legacyCollection']['collectionsPage']['stream']['edges']
                for edge in highlights+streams:
                    if edge['node'].get('url'):
                        url = edge['node']['url']
                    elif edge['node'].get('targetUrl'):
                        url = edge['node']['targetUrl']
                    else:
                        continue
                    if not next((it for it in feed['items'] if it['url'] == url), None):
                        if save_debug:
                            logger.debug('getting content for ' + url)
                        item = get_content(url, args, site_json, save_debug)
                        if item:
                            if utils.filter_item(item, args) == True:
                                feed['items'].append(item)
            feed['items'] = sorted(feed['items'], key=lambda i: i['_timestamp'], reverse=True)

    elif '/live/' in args['url']:
        collection = get_live_feed(url, args, site_json, save_debug)
        if save_debug:
            utils.write_file(collection, './debug/feed.json')

    return feed