import base64, json, re, tldextract
import curl_cffi
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def add_image(image, width=1200):
    orig_src = image['sizes']['original']['url']
    img_src = orig_src.replace('rawImage', '{}x0'.format(width))
    captions = []
    if image.get('caption'):
        captions.append(image['caption']['plain'])
    if image.get('byline'):
        captions.append(image['byline'])
    return utils.add_image(img_src, ' | '.join(captions), link=orig_src)


def add_hst_exco_video(player_id):
    player_url = 'https://player.ex.co/player/' + player_id
    player = utils.get_url_html(player_url)
    if not player:
        return None
    m = re.search(r'window\.STREAM_CONFIGS\[\'{}\'\] = (.*?);\n'.format(player_id), player)
    if not m:
        logger.warning('unable to find STREAM_CONFIGS in ' + player_url)
        return None
    stream_config = json.loads(m.group(1))
    utils.write_file(stream_config, './debug/video.json')
    return utils.add_video(stream_config['contents'][0]['video']['mp4']['src'], 'video/mp4', stream_config['contents'][0]['poster'], stream_config['contents'][0]['title'])


def render_content(content, img_width=1200):
    content_html = ''
    if content['type'] == 'text':
        # if not re.search(r'<strong>RELATED</strong>', content['params']['html1'], flags=re.I):
        #     content_html += content['params']['html1']
        if 'MM_onlineOnly' not in content['params']['html1']:
            content_html += content['params']['html1']

    elif content['type'] == 'image':
        content_html += add_image(content['params'], img_width)

    elif content['type'] == 'gallery':
        content_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
        for slide in content['params']['slides']:
            content_html += '<div style="flex:1; min-width:360px;">' + render_content(slide, 640) + '</div>'
        content_html += '</div>'
        gallery_soup = BeautifulSoup(content_html, 'html.parser')
        gallery_images = []
        for el in gallery_soup.find_all('figure'):
            gallery_images.append({"src": el.a['href'], "caption": el.figcaption.small.decode_contents(), "thumb": el.img['src']})
        gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
        content_html = '<h3><a href="{}">View photo gallery</a></h3>'.format(gallery_url) + content_html

    elif content['type'] == 'video' and content['params']['originalSource'] == 'jwplayer':
        content_html += utils.add_embed(content['params']['playerUrl'])

    elif content['type'] == 'embed':
        if content['params'].get('embedType'):
            if content['params']['embedType'] == 'youtube' or content['params']['embedType'] == 'facebook':
                content_html += utils.add_embed(content['params']['attributes']['iframe_data-url'])
            elif content['params']['embedType'] == 'twitter':
                content_html += utils.add_embed(content['params']['attributes']['a_href'])
            elif content['params']['embedType'] == 'instagram':
                content_html += utils.add_embed(content['params']['attributes']['blockquote_data-instgrm-permalink'])
            elif content['params']['embedType'] == 'commerceconnector':
                soup = BeautifulSoup(content['params']['html2'], 'html.parser')
                img = soup.find('img')
                split_url = urlsplit(content['params']['attributes']['a_href'])
                content_html += '<table><tr><td style="width:200px;"><a href="{}"><img style="width:200px;" src="{}"/></a></td><td style="vertical-align:top;"><a href="{}"><b>{}</b></a><br/>{} | {}</td></tr></table>'.format(content['params']['attributes']['a_href'], content['params']['attributes']['img_src'], content['params']['attributes']['a_href'], img['title'], content['params']['attributes']['a_data-vars-ga-product-custom-brand'], split_url.netloc)
            else:
                logger.warning('unsupported embedType ' + content['params']['embedType'])
        elif content['params'].get('attributes') and content['params']['attributes'].get('div_class') and content['params']['attributes']['div_class'] == 'hst-exco-player':
            pass
        elif content['params'].get('attributes') and content['params']['attributes'].get('script_id') and content['params']['attributes']['script_id'] == 'hst-exco-player-code':
            pass
            # m = re.search(r'playerId = \'([^\']+)\'', content['params']['html1'])
            # if m:
            #     content_html += add_hst_exco_video(m.group(1))
            # else:
            #     logger.warning('unknown hst-exco-player-code playerId')
        elif re.search(r'<iframe', content['params']['html1']):
            m = re.search(r'src="([^"]+)"', content['params']['html1'])
            if m:
                iframe_src = m.group(1)
                if content['params']['attributes'].get('div_class') and content['params']['attributes']['div_class'] == 'hnp-iframe-wrapper':
                    m = re.search(r'iframe-([^-]+)-wrapper', content['params']['attributes']['div_id'])
                    if m:
                        content_html += utils.add_embed('https://cdn.jwplayer.com/players/{}-.js'.format(m.group(1)))
                    else:
                        content_html += utils.add_embed(iframe_src)
                else:
                    content_html += utils.add_embed(iframe_src)
            else:
                logger.warning('unhandled iframe embed')
        else:
            logger.warning('unhandled embed')

    elif content['type'] == 'card':
        content_html += '<h3>{}</h3>'.format(content['params']['title'])
        for it in content['params']['body']:
            content_html += render_content(it)

    elif content['type'] == 'interstitial' and content['params'].get('subtype1') and content['params']['subtype1'] == 'taboola':
        pass

    elif content['type'] == 'ad':
        pass

    else:
        logger.warning('unhandled content type ' + content['type'])

    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    r = curl_cffi.get(url, impersonate="chrome", proxies=config.proxies)
    if r.status_code != 200:
        logger.warning('curl_cffi error HTTPError status code {} getting {}'.format(r.status_code, url))
        return None
    page_soup = BeautifulSoup(r.text, 'lxml')

    if not split_url.path.endswith('.php'):
        page_url = split_url.scheme + '://' + split_url.netloc + split_url.path
        if page_url.endswith('/'):
            page_url = page_url[:-1]
        r = curl_cffi.get(page_url + '/page-data/index/page-data.json', impersonate="chrome", proxies=config.proxies)
        if r.status_code != 200:
            logger.warning('curl_cffi error HTTPError status code {} getting {}'.format(r.status_code, page_url))
            return None
        page_data = json.loads(r.text)
        meta_json = page_data['result']['data']['site']['siteMetadata']['PROJECT']

        item = {}
        item['id'] = meta_json['SLUG']
        item['url'] = meta_json['CANONICAL_URL']
        item['title'] = meta_json['TITLE']
        dt = datetime.fromisoformat(meta_json['ISO_PUBDATE']).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        dt = datetime.fromisoformat(meta_json['ISO_MODDATE']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()
        if meta_json.get('AUTHORS'):
            item['authors'] = [{"name": x['AUTHOR_NAME']} for x in meta_json['AUTHORS']]
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }
        item['tags'] = []
        item['tags'].append(meta_json['HEARST_CATEGORY'])
        if meta_json.get('KEY_SUBJECTS'):
            item['tags'] += [x.strip() for x in meta_json['KEY_SUBJECTS'].split(',')]
        if meta_json.get('IMAGE'):
            item['image'] = meta_json['IMAGE']
        if meta_json.get('DESCRIPTION'):
            item['summary'] = meta_json['DESCRIPTION']

        el = page_soup.find('script', id='gatsby-chunk-mapping')
        if el:
            i = el.string.find('chunkMapping=') + 13
            j = el.string.rfind('};') + 1
            chunk_map = json.loads(el.string[i:j])
            if page_data['componentChunkName'] in chunk_map:
                r = curl_cffi.get(page_url + chunk_map[page_data['componentChunkName']][0], impersonate="chrome", proxies=config.proxies)
                if r.status_code == 200:
                    for m in re.findall(r'exports=JSON\.parse\(\'(.*?)\'\)', r.text):
                        print(m)                        
        return item

    el = page_soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    next_data = json.loads(el.string)
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    meta_json = next_data['props']['pageProps']['page']['meta']
    article_body = None
    article_header = None
    for zone_set in next_data['props']['pageProps']['page']['zoneSets']:
        for zone in zone_set['zones']:
            if zone['id'] == 'zoneBody':
                for widget in zone['widgets']:
                    if widget['id'] == 'articleBody':
                        for it in widget['items']:
                            if it['type'] == 'articleBody':
                                article_body = it
            elif zone['id'] == 'heroZone':
                for widget in zone['widgets']:
                    if widget['id'] == 'articleHeader':
                        for it in widget['items']:
                            if it['type'] == 'articleHeader':
                                article_header = it

    item = {}
    item['id'] = meta_json['id']
    item['url'] = meta_json['canonicalUrl']
    item['title'] = meta_json['title']

    dt = datetime.fromisoformat(meta_json['publicationDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(meta_json['lastModifiedDate'])
    item['date_modified'] = dt.isoformat()

    if article_header and article_header.get('authors'):
        item['authors'] = [{"name": x['name']} for x in article_header['authors']]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    elif meta_json.get('authorName'):
        item['author'] = {
            "name": meta_json['authorName']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
    elif meta_json.get('authorTitle'):
        item['author'] = {
            "name": meta_json['authorTitle']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = [x.strip() for x in meta_json['sections'].split(',')]
    if meta_json.get('newsKeywords'):
        item['tags'] += [x.strip() for x in meta_json['newsKeywords'].split(',')]
    if 'tags' in meta_json:
        if meta_json['tags'].get('keywords'):
            item['tags'] += [x.strip() for x in meta_json['tags']['keywords'].split(',')]
        if meta_json['tags'].get('iabTags'):
            item['tags'] += [x.strip() for x in meta_json['tags']['iabTags'].split(',')]

    if meta_json.get('openGraphImageUrl'):
        item['image'] = meta_json['openGraphImageUrl']

    if meta_json.get('description'):
        item['summary'] = meta_json['description']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    if article_header:
        if article_header.get('subtitle'):
            item['content_html'] += '<p><em>' + article_header['subtitle'] + '</em></p>'
        if article_header.get('hero'):
            if article_header['hero']['type'] == 'image':
                captions = []
                if article_header['hero']['block']['params']['image'].get('caption') and article_header['hero']['block']['params']['image']['caption'].get('plain'):
                    captions.append(article_header['hero']['block']['params']['image']['caption']['plain'])
                if article_header['hero']['block']['params'].get('byline'):
                    captions.append(article_header['hero']['block']['params']['byline'])
                item['content_html'] += utils.add_image(article_header['hero']['block']['params']['image']['url'], ' | '.join(captions))
            else:
                logger.warning('unhandled article hero type {} in {}'.format(article_header['hero']['type'], item['url']))

    if article_body:
        for block in article_body['body']:
            if block['__typename'] == 'TextBlock':
                if block['params']['html1'].startswith('<figure'):
                    soup = BeautifulSoup(block['params']['html1'], 'html.parser')
                    if 'wp-block-image' in soup.figure['class']:
                        captions = []
                        el = soup.find(class_='credit')
                        if el:
                            captions.append(el.decode_contents())
                            el.decompose()
                        if soup.figcaption:
                            captions.insert(0, soup.figcaption.decode_contents())
                        item['content_html'] += utils.add_image(soup.img['src'], ' | '.join(captions))
                    else:
                        logger.warning('unhandled TextBlock figure in ' + item['url'])
                        item['content_html'] += block['params']['html1']
                else:
                    item['content_html'] += block['params']['html1']
            elif block['__typename'] == 'ImageBlock':
                captions = []
                if block['params']['image'].get('caption') and block['params']['image']['caption'].get('plain'):
                    captions.append(block['params']['image']['caption']['plain'])
                if block['params'].get('byline'):
                    captions.append(block['params']['byline'])
                item['content_html'] += utils.add_image(block['params']['image']['url'], ' | '.join(captions))
            elif block['__typename'] == 'GalleryBlock':
                gallery_images = []
                for slide in block['params']['slides']:
                    if slide['type'] == 'image':
                        img_src = slide['params']['image']['url']
                        thumb = slide['params']['image']['url'].replace('rawImage', '960x0').replace('.jpg', '.webp')
                        captions = []
                        if slide['params']['image'].get('caption') and slide['params']['image']['caption'].get('plain'):
                            captions.append(slide['params']['image']['caption']['plain'])
                        if slide['params'].get('byline'):
                            captions.append(slide['params']['byline'])
                        gallery_images.append({"src": img_src, "caption": ' | '.join(captions), "thumb": thumb})
                gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                item['content_html'] += utils.add_image(gallery_images[0]['src'], gallery_images[0]['caption'], link=gallery_url, overlay=config.gallery_button_overlay)
            elif block['__typename'] == 'EmbedBlock':
                soup = BeautifulSoup(block['params']['html1'], 'html.parser')
                if soup.blockquote and 'bluesky-embed' in soup.blockquote['class']:
                    item['content_html'] += utils.add_embed(soup.blockquote['data-bluesky-uri'].replace('at://', 'https://bsky.app/profile/').replace('app.bsky.feed.post', 'post'))
                elif soup.blockquote and 'instagram-media' in soup.blockquote['class']:
                    item['content_html'] += utils.add_embed(soup.blockquote['data-instgrm-permalink'])
                elif soup.iframe:
                    if split_url.netloc in soup.iframe['src'] and '-survey' in soup.iframe['src']:
                        continue
                    item['content_html'] += utils.add_embed(soup.iframe['src'])
                else:
                    logger.warning('unhandled EmbedBlock in ' + item['url'])
            elif block['__typename'] == 'FreeformItemBlock' and 'embed' in block['params'] and block['params']['embed'].get('__id') == 'Datawrapper':
                item['content_html'] += utils.add_embed('https://datawrapper.dwcdn.net/' + block['params']['embed']['__data']['datawrapper_id'] + '/')
            elif block['__typename'] == 'AdBlock' or (block['__typename'] == 'CardBlock' and re.search(r'^(Best of|More)', block['params']['title'], flags=re.I)):
                continue
            else:
                logger.warning('unhandled block type {} in {}'.format(block['__typename'], item['url']))

    # if content_json.get('abstract'):
    #     item['summary'] = content_json['abstract']
    #     item['content_html'] += '<p><em>{}</em></p>'.format(re.sub(r'^<p>(.*)</p>$', r'\1', content_json['abstract']))

    # if content_json['body'][0]['type'] == 'gallery':
    #     item['content_html'] += add_image(content_json['body'][0]['params']['cover'])
    # elif content_json['body'][0]['type'] != 'image' and item.get('_image'):
    #     item['content_html'] += utils.add_image(item['_image'])

    # if content_json['type'] == 'slideshow':
    #     for content in content_json['body']:
    #         if content['type'] == 'gallery':
    #             for slide in content['params']['slides']:
    #                 item['content_html'] += '<h2>{}</h2>'.format(slide['params']['title'])
    #                 item['content_html'] += utils.add_image(slide['params']['sizes']['original']['url'].replace('rawImage', '1000x0'), slide['params']['byline'])
    #                 item['content_html'] += '<p>{}</p>'.format(slide['params']['caption']['html2'])
    #         else:
    #             item['content_html'] += render_content(content)
    # else:
    #     gallery_html = ''
    #     for content in content_json['body']:
    #         if content['type'] == 'gallery':
    #             gallery_html += render_content(content)
    #         elif content['type'] == 'factbox':
    #             item['content_html'] += utils.add_blockquote('<h3 style="margin-top:0;">{}</h3>{}'.format(content_json['factbox']['header'], content_json['factbox']['html1']))
    #         elif content['type'] == 'relatedStories':
    #             item['content_html'] += '<h3 style="margin-bottom:0;">Related stories:</h3><ul style="margin-top:0;">'
    #             for it in content_json['relatedStories']['items']:
    #                 item['content_html'] += '<li><a href="{}">{}</a></li>'.format(it['url'], it['title'])
    #             item['content_html'] += '</ul>'
    #         else:
    #             item['content_html'] += render_content(content)
    #     if gallery_html:
    #         item['content_html'] += '<hr/>' + gallery_html

    # item['content_html'] = re.sub(r'</figure><(figure|table)', r'</figure><br/><\1', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/feed/' in args['url']:
        # https://www.sfgate.com/rss/
        # https://www.seattlepi.com/local/feed/seattlepi-com-Local-News-218.php
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    tld = tldextract.extract(args['url'])

    page_html = utils.get_url_html(args['url'])
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    article_urls = []
    for el in soup.find_all('a', attrs={"data-hdn-analytics": re.compile(r'visit\|article-')}) + soup.find_all('a', class_=re.compile(r'headline')):
        if paths and paths[0] != 'author' and paths[0] not in el['href'].split('/'):
            logger.debug('skipping different section content for ' + el['href'])
            continue
        if el['href'].startswith('/'):
            url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, el['href'])
        else:
            url = el['href']
            if tldextract.extract(url).domain != tld.domain:
                logger.debug('skipping external content for ' + url)
                continue
        if url not in article_urls:
            article_urls.append(url)

    n = 0
    feed_items = []
    for url in article_urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args and n == int(args['max']):
                    break

    feed = utils.init_jsonfeed(args)
    feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
