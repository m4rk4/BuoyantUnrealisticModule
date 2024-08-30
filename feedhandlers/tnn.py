import json, math, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    if url.endswith('.cms'):
        # Doesn't work
        m = re.search(r'/([^/]+)/(\d+)\.cms$', utils.clean_url(url))
    else:
        m = re.search(r'-([^-]+)-(\d+)$', utils.clean_url(url))
    if not m:
        logger.warning('unhandled url ' + url)
        return None

    page_type = ''
    if m.group(1) == 'article':
        content_type = 'articleshow'
    elif m.group(1) == 'video':
        content_type = 'videoshow'
    elif m.group(1) == 'reels':
        content_type = 'shortvideo'
    elif m.group(1) == 'gallery':
        content_type = 'photo-slides'
    elif m.group(1) == 'photostory':
        content_type = 'videoshow'
    elif m.group(1) == 'review':
        content_type = 'articleshow'
        page_type = 'movie'
    elif m.group(1) == 'liveblog':
        content_type = 'liveblog'
    else:
        logger.warning('unhandled content type {} in {}'.format(m.group(1), url))
        return None

    api_url = '{}/request/{}?origin=desktop&msid={}&country_code=US'.format(site_json['api_path'], content_type, m.group(2))
    if page_type:
        api_url += '&page_type=' + page_type
    if site_json.get('hostid'):
        api_url += '&channel_id={}'.format(site_json['hostid'])
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    if content_type == 'articleshow':
        content_json = api_json['response']['sections']['article_show']['data'][0]
    elif content_type == 'videoshow':
        content_json = api_json['response']['sections']['featured']['data'][0]
    elif content_type == 'shortvideo':
        content_json = api_json['response']['sections']['short_video_show']['data'][0]
    elif content_type == 'photo-slides':
        content_json = api_json['response']['sections']['photo_show']['data'][0]
    elif content_type == 'moviereviewsshow':
        content_json = api_json['response']['sections']['article_show']['data'][0]
    elif content_type == 'liveblog':
        content_json = api_json['response']['sections']['live_blog']['data']

    if content_json['cmstype'] == 'PHOTOGALLERYLISTSECTION':
        api_url = '{}/request/photo-slides?origin=desktop&msid={}&country_code=US&type=photolisticle'.format(site_json['api_path'], content_json['msid'])
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/debug.json')
        content_json = api_json['response']['sections']['photo_show']['data'][0]

    item = {}
    item['id'] = content_json['msid']
    item['title'] = content_json['title']

    if content_json.get('seo'):
        item['url'] = content_json['seo']['canonical']
        dt = datetime.fromisoformat(content_json['seo']['datePublished'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        if content_json['seo'].get('dateModified'):
            dt = datetime.fromisoformat(content_json['seo']['dateModified'])
            item['date_modified'] = dt.isoformat()
    else:
        item['url'] = 'https://www.timesnownews.com/' + content_json['seopath']
        dt = datetime.fromtimestamp(content_json['insertdate'] / 1000)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        if content_json.get('updatedate'):
            dt = datetime.fromtimestamp(content_json['updatedate'] / 1000)
            item['date_modified'] = dt.isoformat()

    if content_json.get('authors'):
        authors = []
        for it in content_json['authors']:
            authors.append(it['name'])
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif content_json.get('createdby'):
        item['author'] = {"name": content_json['createdby']}

    if content_json.get('keywords'):
        item['tags'] = []
        for it in content_json['keywords']:
            item['tags'].append(it['name'])

    item['content_html'] = ''
    if content_json['cmstype'] == 'ARTICLE' or content_json['cmstype'] == 'MOVIEREVIEW':
        if content_json.get('synopsis'):
            item['summary'] = content_json['synopsis']
            item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'

        if content_json.get('leadImage'):
            item['_image'] = site_json['image_path'] + '/thumb/msid-{0},thumbsize-{1},width-1280,height-720,resizemode-75/{0}.jpg'.format(content_json['leadImage']['msid'], content_json['leadImage']['thumbsize'])
            if content_json['leadImage'].get('synopsis'):
                caption = re.sub(r'^<p>(.*)</p>$', r'\1', content_json['leadImage']['synopsis'])
            else:
                caption = ''
            item['content_html'] += utils.add_image(item['_image'], caption)
        else:
            item['_image'] = site_json['image_path'] + '/thumb/msid-{0},thumbsize-{1},width-1280,height-720,resizemode-75/{0}.jpg'.format(content_json['msid'], content_json['thumbsize'])
            if content_json['metainfo'].get('TheCaptionOfTheImage'):
                caption = re.sub(r'^<p>(.*)</p>$', r'\1', content_json['metainfo']['TheCaptionOfTheImage']['value'])
            else:
                caption = ''
            item['content_html'] += utils.add_image(item['_image'], caption)

        if content_json['cmstype'] == 'MOVIEREVIEW':
            item['content_html'] += '<p style="text-align:center; font-size:1.5em; font-weight:bold;">' + content_json['metainfo']['MovieName']['value'] + '</p>'
            if content_json['metainfo'].get('CriticRating'):
                item['content_html'] += utils.add_stars(float(content_json['metainfo']['CriticRating']['value']), star_color='red')
            item['content_html'] += '<ul>'
            if content_json['metainfo'].get('MovieReleaseDate'):
                item['content_html'] += '<li>Release Date: ' + utils.format_display_date(datetime.fromtimestamp(int(content_json['metainfo']['MovieReleaseDate']['value']) / 1000), False) + '</li>'
            if content_json['metainfo'].get('MovieCast'):
                item['content_html'] += '<li>Cast: ' + re.sub(r'(\w),(\w)', r'\1, \2', content_json['metainfo']['MovieCast']['value']) + '</li>'
            if content_json['metainfo'].get('MovieDirector'):
                item['content_html'] += '<li>Director: ' + content_json['metainfo']['MovieDirector']['value'] + '</li>'
            if content_json['metainfo'].get('MovieGenere'):
                item['content_html'] += '<li>Genre: ' + re.sub(r'(\w),(\w)', r'\1, \2', content_json['metainfo']['MovieGenere']['value']) + '</li>'
            item['content_html'] += '</ul>'

        if content_json.get('summary'):
            item['content_html'] += '<div>&nbsp;</div><div style="font-size:1.1em; font-weight:bold;">Key Highlights</div>' + content_json['summary']

        if content_json.get('embedData'):
            for block in content_json['embedData']:
                if block.get('photoType'):
                    for it in block['photoType']['list']:
                        img_src = site_json['image_path'] + '/photo/msid-{0}/{0}.jpg'.format(it['msid'])
                        if it.get('synopsis'):
                            caption = re.sub(r'^<p>(.*)</p>$', r'\1', it['synopsis'])
                        else:
                            caption = ''
                        item['content_html'] += utils.add_image(img_src, caption)
                if block.get('htmlText') and block['htmlText'].strip():
                    if 'ispara' in block and block['ispara'] == True:
                        item['content_html'] += '<p>' + block['htmlText'] + '</p>'
                    elif (block['htmlText'].startswith('<strong>ALSO READ:') and block['htmlText'].endswith('</strong>')) or 'timesnownews.com/latest-news' in block['htmlText']:
                        pass
                    else:
                        item['content_html'] += block['htmlText']
                elif block.get('videoType') and block['videoType'].get('list'):
                    split_url = urlsplit(item['url'])
                    video_url = '{}://{}/{}-video-{}'.format(split_url.scheme, split_url.netloc, block['videoType']['list'][0]['seopath'], block['videoType']['list'][0]['msid'])
                    embed_item = get_content(video_url, {"embed": True}, site_json, False)
                    if embed_item:
                        item['content_html'] += embed_item['content_html']
                elif block.get('youtubeList'):
                    item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v=' + block['youtubeList']['id'])
                elif block.get('twitterList'):
                    item['content_html'] += utils.add_embed('https://twitter.com/__/status/' + block['socialId'])
                elif block.get('instagramList'):
                    m = re.search(r'data-instgrm-permalink="([^"]+)"', block['instagramList'])
                    item['content_html'] += utils.add_embed(m.group(1))
                elif not block.get('photoType'):
                    logger.warning('unhandled embedData block in ' + item['url'])
                    # print(str(block))
            item['content_html'] = re.sub(r'(<h\d) style="[^"]+"', r'\1', item['content_html'])
    elif content_json['cmstype'] == 'MEDIAVIDEO' or content_json['cmstype'] == 'SHORTMEDIAVIDEO':
        video_url = 'https://tvid.in/api/mediainfo/vq/b7/{0}/{0}.json?vj=105&apikey=tgbsl486web5ab8uukl9o&k={0}&mse=1&aj=31&ajbit=00000&pw=716&ph=403&url={1}&sw=1920&sh=1200&cont=masterVideoPlayer{0}&gdprn=2&skipanalytics=2&map=1&sdk=1&viewportvr=100'.format(content_json['media']['id'], quote_plus(item['url']))
        video_json = utils.get_url_json(video_url)
        if video_json:
            if save_debug:
                utils.write_file(video_json, './debug/video.json')
            video = next((it for it in video_json['flavors'] if it['type'] == 'hls'), None)
            if video:
                item['content_html'] += utils.add_video('https:' + video['url'], 'application/x-mpegURL', 'https:' + video_json['poster'], video_json['name'])
            else:
                video = next((it for it in video_json['flavors'] if it['type'] == 'mp4'), None)
                item['content_html'] += utils.add_video('https:' + video['url'], 'video/mp4', 'https:' + video_json['poster'], video_json['name'])
        if 'embed' not in args and content_json.get('synopsis'):
            item['summary'] = content_json['synopsis']
            item['content_html'] += '<p>' + re.sub(r'<br\s?/?>\s?<br\s?/?>', '</p><p>', item['summary']) + '</p>'
    elif content_json['cmstype'] == 'PHOTOGALLERYSLIDESHOWSECTION' or content_json['cmstype'] == 'PHOTOGALLERYLISTSECTION':
        if content_json.get('synopsis'):
            item['summary'] = content_json['synopsis']
            item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'
        gallery_html = ''
        gallery_images = []
        for i, slide in enumerate(content_json['slides']):
            if slide['widgetType'] == 'PHOTO_SLIDE':
                img_src = site_json['image_path'] + '/photo/msid-{0}/{0}.jpg'.format(slide['msid'])
                thumb = img_src + '?quality=60'
                if not item.get('_image'):
                    item['_image'] = img_src
                if slide.get('agency') and slide['agency'].get('name'):
                    caption = slide['agency']['name']
                else:
                    caption = ''
                desc = ''
                if slide.get('title'):
                    desc += '<p style="font-size:1.1em; font-weight:bold;">' + slide['title'] + '</p>'
                if slide.get('synopsis'):
                    desc += slide['synopsis']
                if i == 0:
                    gallery_html += utils.add_image(img_src + '?quality=60', caption, link=img_src, desc=desc)
                    gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                else:
                    gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src, desc=desc) + '</div>'
                gallery_images.append({"src": img_src, "caption": caption, "desc": desc, "thumb": thumb})
            elif slide['widgetType'] == 'ad':
                pass
            else:
                logger.warning('unhandled slide widgetType {} in {}'.format(slide['widgetType'], item['url']))
        gallery_html += '</div>'
        gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
        item['content_html'] += '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html
    elif content_json['cmstype'] == 'LIVEBLOG':
        if content_json['metainfo'].get('Prefix') and content_json['metainfo']['Prefix'].get('value'):
            item['content_html'] += '<p><em>' + content_json['metainfo']['Prefix']['value'] + '</em></p>'

        if content_json.get('score_card_list'):
            item['content_html'] += '<table style="width:100%; border:1px solid #ccc; margin:1em;"><tr>'
            item['content_html'] += '<td style="width:48px; text-align:center;"><img src="{0}/thumb/msid-{1},width-48,height-34,resizemode-75/{1}.jpg"/><br/><b>{2}</b></td>'.format(site_json['image_path'], content_json['score_card_list']['team1_msid'], content_json['score_card_list']['team1_short'])
            item['content_html'] += '<td style="width:48px; text-align:center;"><img src="{0}/thumb/msid-{1},width-48,height-34,resizemode-75/{1}.jpg"/><br/><b>{2}</b></td>'.format(site_json['image_path'], content_json['score_card_list']['team2_msid'], content_json['score_card_list']['team2_short'])
            item['content_html'] += '</tr></table>'

        item['_image'] = site_json['image_path'] + '/thumb/msid-{0},thumbsize-{1},width-1280,height-720,resizemode-75/{0}.jpg'.format(content_json['msid'], content_json['thumbsize'])
        item['content_html'] += utils.add_image(item['_image'], item['title'])
        item['summary'] = content_json['synopsis']
        item['content_html'] += '<p>' + re.sub(r'<br\s?/?>\s?<br\s?/?>', '</p><p>', item['summary']) + '</p>'

        if content_json.get('children'):
            for block in content_json['children']:
                dt = datetime.fromtimestamp(block['insertdate'] / 1000)
                item['content_html'] += '<div style="line-height:1.5em;"><span style="color:red; border:1px solid red; line-height:1em; padding:4px; font-size:0.8em;">' + utils.format_display_date(dt) + '</span></div>'
                item['content_html'] += '<div style="border-left:2px solid #ccc; margin-left:8px; padding-left:8px; padding-top:8px;">'
                if block['cmstype'] == 'SLIDE':
                    if block.get('title'):
                        item['content_html'] += '<div><strong>' + block['title'] + '</strong></div>'
                    if 'twitter-tweet' in block['text']:
                        m = re.findall(r'href="([^"]+)"', block['text'])
                        item['content_html'] += '<div>&nbsp;</div>' + utils.add_embed(m[-1])
                    else:
                        logger.warning('unhandled child SLIDE block in ' + item['url'])
                elif block['cmstype'] == 'TEXTSNIPPET':
                    if block.get('title'):
                        item['content_html'] += '<div><strong>' + block['title'] + '</strong></div>'
                    item['content_html'] += '<p>' + block['synopsis'] + '</p>'
                elif block['cmstype'] == 'SCORECARD':
                    if block.get('score') and block['score'] != 0:
                        score = block['score'].split('/')
                        team = ''
                        if len(score) == 2:
                            if int(score[0]) > int(score[1]):
                                team = content_json['match_info']['team2_short_name']
                            else:
                                team = content_json['match_info']['team1_short_name']
                        if int(block['runs']) >= 6:
                            color = '#008cb5'
                        elif int(block['runs']) >= 4:
                            color = '#00b56f'
                        else:
                            color = '#393939'
                        item['content_html'] += '<div><div style="display:inline-block; border-radius:50%; width:1.2em; height:1.2em; padding:4px; background:{}; color:white; text-align:center; font-size:1.5em; font-weight:bold; vertical-align:middle;">{}</div>&nbsp;<strong>{} - {}</strong> <small style="color:#555;">{} OVERS</small></div>'.format(color, block['runs'], team, block['score'], block['over'])
                    item['content_html'] += '<div>' + block['synopsis'] + '</div>'
                elif block['cmstype'] == 'POLL':
                    item['content_html'] += '<div><strong>' + block['title'] + '</strong></div><div>&nbsp;</div>'
                    for it in block['polloptions']:
                        item['content_html'] += '<div><input type="radio" id="optionno{0}" name="poll"><label for="optionno{0}">{1}</label></div>'.format(it['optionno'], it['description'])
                item['content_html'] += '<div>&nbsp;</div></div>'
    elif content_json['cmstype'] == 'IMAGES' and 'web-stories' in item['url']:
        item['url'] = url
        page_html = utils.get_url_html(item['url'])
        if save_debug:
            utils.write_file(page_html, './debug/debug.html')
        page_soup = BeautifulSoup(page_html, 'lxml')
        for el in page_soup.find_all('script', attrs={"type": "application/ld+json"}):
            ld_json = json.loads(el.string.replace('\n', ''))
            if ld_json.get('@type') and ld_json['@type'] == 'MediaGallery':
                if save_debug:
                    utils.write_file(ld_json, './debug/ld_json.json')
                item['_image'] = ld_json['mainEntityOfPage']['associatedMedia'][0]['contentUrl']
                if ld_json.get('description'):
                    item['summary'] = ld_json['description']
                # print(ld_json['mainEntityOfPage']['associatedMedia'][-1])
                gallery_images = []
                gallery_html = ''
                for i, it in enumerate(ld_json['mainEntityOfPage']['associatedMedia']):
                    if it['@type'] == 'ImageObject':
                        img_src = it['contentUrl']
                        thumb = it['thumbnailUrl']
                        desc = ''
                        if it.get('name'):
                            desc += '<p style="font-size:1.1em; font-weight:bold;">' + it['name'] + '</p>'
                        if it.get('description'):
                            desc += '<p>' + it['description'] + '</p>'
                        elif it.get('caption'):
                            desc += '<p>' + it['caption'] + '</p>'
                        if i == 0:
                            gallery_html += utils.add_image(thumb, link=img_src, desc=desc)
                            gallery_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                        else:
                            gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, link=img_src, desc=desc) + '</div>'
                        gallery_images.append({"src": img_src, "caption": "", "desc": desc, "thumb": thumb})
                gallery_html += '</div>'
                gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                item['content_html'] += '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html
                break

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
