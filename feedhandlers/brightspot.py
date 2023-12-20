import json, math, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


# Compatible sites
# https://scripps.com/our-brands/local-media/

def add_video(video):
    sources = []
    caption = ''
    poster = ''
    if video.get('sources'):
        sources = video['sources']
    elif video['_template'] == '/pbs/player/PbsPartnerProvider.hbs':
        m = re.search(r'src=\'([^\']+)\'', video['embedCode'])
        if m:
            page_html = utils.get_url_html('https:' + m.group(1))
            if page_html:
                soup = BeautifulSoup(page_html, 'lxml')
                el = soup.find('script', string=re.compile(r'window\.videoBridge'))
                if el:
                    i = el.string.find('{', el.string.find('window.videoBridge'))
                    j = el.string.rfind('}') + 1
                    video_json = json.loads(el.string[i:j])
                    if video_json.get('short_description'):
                        caption = video_json['short_description']
                    if video_json.get('image_url'):
                        poster = video_json['image_url']
                    if video_json.get('encodings'):
                        for it in video_json['encodings']:
                            source = {}
                            if '/redirect/' in it:
                                source['src'] = utils.get_redirect_url(it)
                            else:
                                source['src'] = it
                            if '.mp4' in source['src']:
                                source['type'] = 'mp4'
                            else:
                                source['type'] = 'm3u8'
                            sources.append(source)

    if sources:
        source = next((it for it in sources if it['type'] == 'mp4'), None)
        if source:
            video_src = source['src']
            video_type = 'video/mp4'
        else:
            source = next((it for it in sources if it['type'] == 'm3u8'), None)
            if source:
                video_src = source['src']
                video_type = 'application/x-mpegURL'
    else:
        logger.warning('unknown video source')
        return ''

    if not caption:
        if video.get('caption'):
            caption = video['caption']

    if not poster:
        if video.get('thumbnailUrl'):
            poster = video['thumbnailUrl']
        elif video.get('thumbnail'):
            poster = video['thumbnail'][0]['image']['src']
    return utils.add_video(video_src, video_type, poster, caption)


def add_image(image):
    captions = []
    if image.get('caption'):
        if isinstance(image['caption'], str):
            captions.append(image['caption'])
        elif isinstance(image['caption'], list):
            for caption in image['caption']:
                for it in caption['items']:
                    captions.append(re.sub(r'^<p>(.*)</p>$', r'\1', it))
    if image.get('credit'):
        if isinstance(image['credit'], str):
            captions.append(image['credit'])
        elif isinstance(image['credit'], list):
            for caption in image['credit']:
                for it in caption['items']:
                    captions.append(re.sub(r'^<p>(.*)</p>$', r'\1', it))
    return utils.add_image(image['image']['src'], ' | '.join(captions))


def render_content(content, skip_promos=True):
    content_html = ''
    if isinstance(content, str):
        def sub_img(matchobj):
            return utils.add_image(matchobj.group(1))
        content_html += re.sub(r'<p><img[^>]*src="([^"]+)"[^>]*></p>', sub_img, content)
    elif content.get('_template'):
        if '/article/RichTextArticleBody.hbs' in content['_template']:
            for it in content['body']:
                content_html += render_content(it, skip_promos)
        elif '/text/RichTextHeading.hbs' in content['_template']:
            content_html += '<{}>'.format(content['tag'])
            if content.get('text'):
                if isinstance(content['text'], str):
                    content_html += content['text']
                elif isinstance(content['text'], list):
                    for it in content['text']:
                        content_html += render_content(it, skip_promos)
            content_html += '</{}>'.format(content['tag'])
        elif '/rte/HorizontalRule.hbs' in content['_template'] or '/divider/Divider.hbs' in content['_template']:
            content_html += '<hr/>'
        elif '/text/RichTextModule.hbs' in content['_template']:
            for it in content['items']:
                content_html += render_content(it, skip_promos)
        elif '/enhancement/Enhancement.hbs' in content['_template'] or '/externalcontent/ExternalContentWrapper.hbs' in content['_template']:
            for it in content['item']:
                content_html += render_content(it, skip_promos)
        elif '/enhancement/InlineEnhancement.hbs' in content['_template']:
            if content.get('items'):
                for it in content['items']:
                    content_html += render_content(it, skip_promos)
            elif content.get('item'):
                for it in content['item']:
                    content_html += render_content(it, skip_promos)
        elif '/module/ModuleType.hbs' in content['_template']:
            for it in content['content']:
                content_html += render_content(it, skip_promos)
        elif '/link/Link.hbs' in content['_template'] or '/link/LinkEnhancement.hbs' in content['_template']:
            if content.get('body'):
                content_html += '<a href="{}">'.format(content['href'])
                if isinstance(content['body'], str):
                    content_html += content['body']
                elif isinstance(content['body'], list):
                    for body in content['body']:
                        for it in body['items']:
                            content_html += render_content(it, skip_promos)
                content_html += '</a>'
            else:
                logger.warning('unhandled Link content')
                # print(content)
        elif '/quote/Quote.hbs' in content['_template'] or '/quote/QuoteEnhancement.hbs' in content['_template']:
            content_html += utils.add_pullquote(content['quote'], content.get('attribution'))
        elif '/pullquote/PullQuote.hbs' in content['_template']:
            quote = ''
            for it in content['quote']:
                quote += render_content(it, skip_promos)
            # TODO: attribution?
            content_html += utils.add_pullquote(quote, content.get('attribution'))
        elif '/list/List.hbs' in content['_template']:
            if content.get('title'):
                content_html += '<h4>{}</h4>'.format(content['title'])
            if not skip_promos:
                for it in content['items']:
                    content_html += render_content(it, skip_promos)
            else:
                content_html += '<ul>'
                for it in content['items']:
                    content_html += '<li>{}</li>'.format(render_content(it, skip_promos))
                content_html += '</ul>'
        elif '/promo/Promo.hbs' in content['_template']:
            if not skip_promos:
                if content.get('title') and content.get('url'):
                    if content.get('media'):
                        content_html += '<table><tr><td><a href="{}"><img src="{}" style="width:200px;" /></a></td><td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold"><a href="{}">{}</a></div>'.format(content['url'], content['media'][0]['image']['src'], content['url'], content['title'])
                        if content.get('description'):
                            content_html += '<div style="font-size:0.8em;">{}</div>'.format(content['description'])
                        content_html += '</td></tr></table>'
                    else:
                        content_html += '<a href="{}">{}</a>'.format(content['url'], content['title'])
                else:
                    logger.warning('unhandled Promo type ' + content['type'])
            else:
                logger.debug('skipping Promo ' + content.get('url'))
        elif '/image/ImageEnhancement.hbs' in content['_template']:
            for it in content['item']:
                content_html += render_content(it, skip_promos)
        elif '/figure/Figure.hbs' in content['_template'] or '/image/Image.hbs' in content['_template'] or '/image/Picture.hbs' in content['_template']:
            content_html += add_image(content)
        elif '/carousel/Carousel.hbs' in content['_template']:
            for it in content['slides']:
                content_html += render_content(it, skip_promos)
        elif '/gallery/GallerySlide.hbs' in content['_template']:
            captions = []
            if content.get('infoDescription'):
                captions.append(content['infoDescription'])
            if content.get('infoAttribution'):
                captions.append(content['infoAttribution'])
            if '/image/Image.hbs' in content['mediaContent'][0]['_template'] or '/image/Picture.hbs' in content['mediaContent'][0]['_template']:
                content_html += utils.add_image(content['mediaContent'][0]['image']['src'], ' | '.join(captions))
            else:
                logger.warning('unhandled GallerySlide media type ' + content['mediaContent'][0]['_template'])
        elif '/mediaset/MediaSet.hbs' in content['_template']:
            for it in content['set']:
                content_html += render_content(it, skip_promos)
        elif '/mediaset/MediaSetEntry.hbs' in content['_template']:
            if content.get('image'):
                # TODO: credit/attribution?
                content_html += utils.add_image(content['image'][0]['image']['src'], content.get('caption'))
            else:
                logger.warning('unhandled MediaSetEntry media type ' + content['mediaContent'][0]['_template'])
        elif '/video/VideoEnhancement.hbs' in content['_template'] or '/video/VideoLead.hbs' in content['_template']:
            # content_html += add_video(content['player'][0])
            content_html += render_content(content['player'][0], skip_promos)
        elif '/video/HTML5VideoPlayer.hbs' in content['_template'] or '/wheel/WheelItemVideo.hbs' in content['_template']:
            source = next((it for it in content['sources'] if 'mp4' in it['src']), None)
            if source:
                video_src = source['src']
                video_type = 'video/mp4'
            else:
                source = next((it for it in content['sources'] if 'm3u8' in it['src']), None)
                if source:
                    video_src = source['src']
                    video_type = 'application/x-mpegURL'
            if source:
                if content.get('thumbnailUrl'):
                    poster = content['thumbnailUrl']
                elif content.get('thumbnail'):
                    poster = content['thumbnail'][0]['image']['src']
                else:
                    poster = ''
                if content.get('caption'):
                    caption = content['caption']
                elif content.get('title'):
                    caption = content['title']
                else:
                    caption = ''
                content_html += utils.add_video(video_src, video_type, poster, caption)
            else:
                logger.warning('unhandled HTML5VideoPlayer content')
        elif '/gvp/GrapheneVideoPlayer.hbs' in content['_template']:
            # There may be multiple bitrate sources, we only get the first - need to parse the source filename
            # The m3u8 files give a CORS error on localhost
            source = next((it for it in content['videoSourcesList'] if 'mp4' in it['type']), None)
            if not source:
                source = next((it for it in content['videoSourcesList'] if 'mpegURL' in it['type']), None)
            if source:
                content_html += utils.add_video(source['src'], source['type'], content['poster']['src'], content['videoTitle'])
            else:
                logger.warning('unhandled GrapheneVideoPlayer content')
        elif '/mpx/MpxVideoPlayer.hbs' in content['_template']:
            if content.get('src'):
                video_src = utils.get_redirect_url(content['src'])
                video_type = 'video/mp4'
            elif content.get('hlsUrl'):
                video_src = utils.get_redirect_url(content['hlsUrl'])
                video_type = 'application/x-mpegURL'
            else:
                video_src = ''
            if video_src:
                if content.get('videoTitle'):
                    caption = content['videoTitle']
                elif content.get('videoDescription'):
                    caption = content['videoDescription']
                else:
                    caption = ''
                content_html += utils.add_video(video_src, video_type, content['poster'][0]['image']['src'], caption)
            else:
                logger.warning('unhandled MpxVideoPlayer content')
        elif '/player/PbsPartnerProvider.hbs' in content['_template']:
            new_html = ''
            m = re.search(r'src=\'([^\']+)\'', content['embedCode'])
            if m:
                page_html = utils.get_url_html('https:' + m.group(1))
                if page_html:
                    soup = BeautifulSoup(page_html, 'lxml')
                    el = soup.find('script', string=re.compile(r'window\.videoBridge'))
                    if el:
                        i = el.string.find('{', el.string.find('window.videoBridge'))
                        j = el.string.rfind('}') + 1
                        video_json = json.loads(el.string[i:j])
                        sources = []
                        if video_json.get('encodings'):
                            for it in video_json['encodings']:
                                source = {}
                                if '/redirect/' in it:
                                    source['src'] = utils.get_redirect_url(it)
                                else:
                                    source['src'] = it
                                if '.mp4' in source['src']:
                                    source['type'] = 'video/mp4'
                                else:
                                    source['type'] = 'application/x-mpegURL'
                                sources.append(source)
                        if sources:
                            source = next((it for it in sources if 'mp4' in it['type']), None)
                            if not source:
                                source = next((it for it in sources if 'x-mpegURL' in it['type']), None)
                            if video_json.get('short_description'):
                                caption = video_json['short_description']
                            else:
                                caption = ''
                            if video_json.get('image_url'):
                                poster = video_json['image_url']
                            else:
                                poster = ''
                            new_html += utils.add_video(source['src'], source['type'], poster, caption)
            if new_html:
                content_html += new_html
            else:
                logger.warning('unhandled /player/PbsPartnerProvider.hbs')
        elif '/youtube/YouTubeVideoPlayer.hbs' in content['_template']:
            content_html += utils.add_embed('https://www.youtube.com/watch?v=' + content['videoId'])
        elif content['_template'] == '/twitter/TweetUrl.hbs':
            if content.get('postUrl'):
                content_html += utils.add_embed(content['postUrl'])
            elif content.get('oEmbed'):
                soup = BeautifulSoup(content['oEmbed'], 'html.parser')
                links = soup.find_all('a')
                content_html += utils.add_embed(links[-1]['href'])
            elif content.get('externalContent'):
                soup = BeautifulSoup(content['externalContent'], 'html.parser')
                links = soup.find_all('a')
                content_html += utils.add_embed(links[-1]['href'])
            elif content.get('postId'):
                # There was a case where the postId was incorrect
                content_html += utils.add_embed('https://twitter.com/__/status/' + content['postId'])
        elif content['_template'] == '/twitter/TweetEmbed.hbs':
            soup = BeautifulSoup(content['embedCode'], 'html.parser')
            links = soup.find_all('a')
            content_html += utils.add_embed(links[-1]['href'])
        elif content['_template'] == '/instagram/InstagramUrl.hbs':
            if content.get('oEmbed') and content['oEmbed'].startswith('<blockquote'):
                m = re.search(r'data-instgrm-permalink="([^"]+)"', content['oEmbed'])
                content_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled InstagramUrl content')
        elif content['_template'] == '/instagram/InstagramEmbed.hbs':
            m = re.search(r'data-instgrm-permalink="([^"]+)"', content['embedCode'])
            if m:
                content_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled InstagramEmbed content')
        elif content['_template'] == '/facebook/FacebookEmbed.hbs' or content['_template'] == '/facebook/FacebookUrl.hbs':
            content_html += utils.add_embed(content['postUrl'])
        elif content['_template'] == '/core/iframe/IframeModule.hbs' or content['_template'] == '/module/IframeModule.hbs':
            if content['url'].startswith('//'):
                src = 'https:' + content['url']
            else:
                src = content['url']
            if src.endswith('.pdf'):
                content_html += utils.add_embed('https://drive.google.com/viewerng/viewer?url=' + quote_plus(src))
            else:
                content_html += utils.add_embed(src)
        elif '/externalcontent/ExternalContent.hbs' in content['_template']:
            new_html = ''
            if content['oEmbed'].startswith('<iframe'):
                m = re.search(r'src="([^"]+)"', content['oEmbed'])
                if m:
                    new_html += utils.add_embed(m.group(1))
            elif content['oEmbed'].startswith('<blockquote'):
                if 'twitter-tweet' in content['oEmbed']:
                    soup = BeautifulSoup(content['oEmbed'], 'html.parser')
                    links = soup.find_all('a')
                    new_html += utils.add_embed(links[-1]['href'])
            if new_html:
                content_html += new_html
            else:
                logger.warning('unhandled ExternalContent content')
        elif '/interactive/InteractiveProject.hbs' in content['_template']:
            if content.get('url') and 'datawrapper.dwcdn.net' in content['url']:
                if content['url'].startswith('//'):
                    link = 'https:' + content['url']
                else:
                    link = content['url']
                content_html += utils.add_embed(link)
            else:
                logger.warning('unhandled InteractiveProject content')
        elif '/transcript/Transcript.hbs' in content['_template']:
            for it in content['text']:
                content_html += render_content(it, skip_promos)
        elif '/rating/RatingCard.hbs' in content['_template']:
            # https://chicago.suntimes.com/movies-and-tv/2023/11/15/23959832/hunger-games-ballad-review-songbirds-snakes-prequel-coriolanus-snow-tom-blyth-rachel-zegler
            content_html += '<div style="text-align:center;"><div style="display:inline-block; margin-left:auto; margin-right:auto; padding:8px; background-color:#ccc;"><div style="font-size:1.1em; font-weight:bold;">{}</div><hr/><div style="font-size:2em; font-weight:bold;">'.format(content['title'])
            rating = float(content['rating'])
            for i in range(math.floor(rating)):
                content_html += '★'
            if rating % 1 != 0:
                content_html += '½'
            for i in range(4 - math.ceil(rating)):
                content_html += '☆'
            content_html += '</div></div></div>'
        elif '/answerbox/AnswerBox.hbs' in content['_template']:
            content_html = '<table style="padding:1em; background-color:#ccc;"><tr>'
            if content.get('leadImage'):
                content_html += '<td style="vertical-align:top;"><img src="{}" style="width:200px;" /></td>'.format(content['leadImage'][0]['image']['src'])
            content_html += '<td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold">{}</div><div style="font-size:0.9em;">{}</div></td></tr></table>'.format(content['title'], content['description'])
        elif '/infobox/Infobox.hbs' in content['_template']:
            new_html = ''
            if content.get('image'):
                new_html += '<div><img src="{}" style="width:100%;"/></div>'.format(content['image'][0]['image']['src'])
            if content.get('description'):
                new_html += '<p>{}</p>'.format(content['description'])
            if content.get('items'):
                new_html += '<ul>'
                for it in content['items']:
                    new_html += '<li>' + render_content(it) + '</li>'
                new_html += '</ul>'
            content_html += utils.add_blockquote(new_html)
        elif '/promoAnchor/PromoAnchor.hbs' in content['_template']:
            content_html = '<table style="margin-left:auto; margin-right:auto; padding:1em; border:1px solid black;"><tr>'
            if content.get('image'):
                content_html += '<td style="vertical-align:top;"><img src="{}" style="width:200px;" /></td>'.format(content['image'][0]['image']['src'])
            content_html += '<td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold"><a href="{}">{}</a></div>'.format(content['link']['url'], content['title'])
            if content.get('description'):
                content_html += '<div style="font-size:0.9em;">{}</div>'.format(content['description'])
            content_html += '</td></tr></table>'
        elif '/text/RichTextSidebarModule.hbs' in content['_template']:
            new_html = ''
            for it in content['items']:
                new_html += render_content(it, skip_promos)
            if new_html and new_html != '<p></p>':
                content_html += '<blockquote style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;">{}</blockquote>'.format(new_html)
        elif '/htmlmodule/HtmlModuleEnhancement.hbs' in content['_template']:
            for it in content['htmlModule']:
                content_html += render_content(it, skip_promos)
        elif '/listicle/ListicleItem.hbs' in content['_template']:
            content_html += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
            if content.get('title'):
                content_html += '<h2>'
                for it in content['title']:
                    content_html += render_content(it, skip_promos)
                content_html += '</h2>'
            if content.get('body'):
                for it in content['body']:
                    content_html += render_content(it, skip_promos)
        elif '/liveblog/LiveBlogPost.hbs' in content['_template']:
            blog_item = get_item(content, {}, None, False)
            if blog_item:
                content_html += '<div>&nbsp;</div><hr/><div>&nbsp;</div><div>Update: {}'.format(blog_item['_display_date'])
                if blog_item.get('author'):
                    content_html += '<br/>By ' + blog_item['author']['name']
                content_html += '</div><h2>{}</h2>{}'.format(blog_item['title'], blog_item['content_html'])
        elif '/container/Container.hbs' in content['_template']:
            for it in content['columns']:
                content_html += render_content(it, skip_promos)
        elif '/container/ThreeColumnContainer.hbs' in content['_template']:
            content_html += '<div style="display:flex; flex-wrap:wrap; align-items:flex-start; gap:1em;"><div style="flex:1; min-width:200; max-width:240px; padding:8px;">'
            for it in content['columnOne']:
                content_html += render_content(it, False)
            content_html += '</div><div style="flex:1; min-width:200; max-width:240px; padding:8px;">'
            for it in content['columnTwo']:
                content_html += render_content(it, False)
            content_html += '</div><div style="flex:1; min-width:200; max-width:240px; padding:8px;">'
            for it in content['columnThree']:
                content_html += render_content(it, False)
            content_html += '</div></div>'
        elif '/pyminteractive/PymInteractive.hbs' in content['_template']:
            if 'www.emailmeform.com' in content['html']:
                m = re.search(r'src="([^"]+)"', content['html'])
                paths = list(filter(None, urlsplit(m.group(1)).path[1:].split('/')))
                link = 'https://www.emailmeform.com/builder/embed/' + paths[-1]
                content_html += '<blockquote><b>Embedded content from <a href="{0}">{0}</a></b></blockquote>'.format(link)
            else:
                logger.warning('unhandled PymInteractive content')
        elif '/htmlmodule/HtmlModule.hbs' in content['_template'] or '/module/HtmlModule.hbs' in content['_template']:
            if not re.search(r'download our apps|TOP STORIES|window\.om\d+|piano-sidebar-newsletter|^<style>.*</style>$', content['rawHtml'], flags=re.I|re.S):
                if content['rawHtml'].startswith('<iframe'):
                    m = re.search(r'src="([^"]+)"', content['rawHtml'])
                    if m:
                        content_html += utils.add_embed(m.group(1))
                    else:
                        logger.warning('unknown rawHtml content')
                elif '<script' not in content['rawHtml'] and '<style' not in content['rawHtml']:
                    content_html += content['rawHtml']
                else:
                    logger.warning('unknown rawHtml content')
                    print(content['rawHtml'])
        elif content['_template'] == '/customEmbed/EarlyElements.hbs' or content['_template'] == '/customEmbed/CustomEmbedModule.hbs':
            if not re.search(r'OUTBRAIN|Report a typo|ubscribe to', content['html'], flags=re.I):
                logger.warning('unknown customEmbed content')
        elif '/ad/' in content['_template'] or 'AdModule' in content['_template'] or '/taboola/' in content['_template'] or '/nativo/NativoModule.hbs' in content['_template'] or '/relatedlist/RelatedList.hbs' in content['_template'] or '/form/Form.hbs' in content['_template'] or '/promo/PromoRichTextElement.hbs' in content['_template'] or '/newsletter/NewsletterModule.hbs' in content['_template']:
            pass
        else:
            logger.warning('unhandled content template ' + content['_template'])
    elif content.get('items'):
        for it in content['items']:
            content_html += render_content(it, skip_promos)
    else:
        logger.warning('unhandled content block')
    return content_html


def get_content(url, args, site_json, save_debug=False):
    article_json = utils.get_url_json(utils.clean_url(url) + '?_renderer=json')
    if not article_json:
        return None
    return get_item(article_json, args, site_json, save_debug)


def get_item(article_json, args, site_json, save_debug):
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    if article_json.get('meta'):
        meta_json = next((it for it in article_json['meta'] if it['_template'] == '/facebook/OpenGraphMeta.hbs'), None)
    else:
        meta_json = None

    item = {}

    if article_json['_template'] != '/liveblog/LiveBlogPost.hbs':
        item['id'] = article_json['contentId']
        if meta_json:
            item['url'] = meta_json['url']
        else:
            item['url'] = article_json['canonicalLink']

    if isinstance(article_json['headline'], str):
        item['title'] = article_json['headline']
    elif isinstance(article_json['headline'], list):
        item['title'] = article_json['headline'][0]['items'][0]

    dt = datetime.fromisoformat(article_json['datePublishedISO'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    short_display_date = utils.format_display_date(dt, False)

    if article_json.get('dateModifiedISO'):
        dt = datetime.fromisoformat(article_json['dateModifiedISO'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()
    elif article_json.get('updateDate'):
        date = re.sub('(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})([-+])(\d+)', r'\1-\2-\3T\4:\5:\6\7\8:00', article_json['updateDate'])
        dt = datetime.fromisoformat(date).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    if article_json.get('people'):
        for it in article_json['people']:
            if it['type'] == 'author':
                authors.append(it['title'])
    elif article_json.get('authors'):
        for it in article_json['authors']:
            if it.get('name'):
                if isinstance(it['name'], str):
                    authors.append(it['name'])
                elif isinstance(it['name'], list):
                    authors.append(it['name'][0]['items'][0])
            elif it.get('body'):
                authors.append(it['body'])
    elif article_json.get('authorsInfo'):
        for it in article_json['authorsInfo']:
            authors.append(it['authorName'])
    elif article_json.get('authorName'):
        if isinstance(article_json['authorName'], str):
            authors.append(article_json['authorName'])
        elif isinstance(article_json['authorName'], list):
            for it in article_json['authorName']:
                authors.append(render_content(it))
    elif article_json.get('bylineText'):
        authors = re.split(r', | and ', article_json['bylineText'])
    if article_json.get('contributingAuthorsInfo'):
        for it in article_json['contributingAuthorsInfo']:
            authors.append(it['authorName'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    if article_json.get('sourceOrganizationName'):
        item['author']['name'] += ' ({})'.format(article_json['sourceOrganizationName'])

    item['tags'] = []
    if meta_json and meta_json.get('type') and meta_json['type'][0].get('tags'):
        item['tags'] = meta_json['type'][0]['tags'].copy()
    if article_json.get('keywords'):
        item['tags'] += article_json['keywords'].split(',')
    if article_json.get('primarySection'):
        if isinstance(article_json['primarySection'][0]['body'], str):
            item['tags'].append(article_json['primarySection'][0]['body'])
        elif isinstance(article_json['primarySection'][0]['body'], list):
            for it in article_json['primarySection'][0]['body']:
                item['tags'].append(render_content(it))
    if article_json.get('secondarySections'):
        for section in article_json['secondarySections']:
            if isinstance(section['body'], str):
                item['tags'].append(section['body'])
            elif isinstance(section['body'], list):
                for it in section['body']:
                    item['tags'].append(render_content(it))
    if meta_json and meta_json.get('type'):
        for it in meta_json['type']:
            if it.get('section') and it['section'] not in item['tags']:
                item['tags'].append(it['section'])
    if not item.get('tags'):
        del item['tags']

    if article_json.get('description'):
        item['summary'] = article_json['description']
    elif meta_json and meta_json.get('description'):
        item['summary'] = meta_json['description']

    content_html = ''
    if article_json.get('subHeadline'):
        if isinstance(article_json['subHeadline'], str):
            content_html += '<p><em>{}</em></p>'.format(article_json['subHeadline'])
        elif isinstance(article_json['subHeadline'], list):
            content_html += '<p><em>'
            for it in article_json['subHeadline']:
                content_html += render_content(it)
            content_html += '</em></p>'

    if '/gallery/GalleryPage.hbs' in article_json['_template']:
        item['_image'] = article_json['slides'][0]['mediaContent'][0]['image']['src']
        for content in article_json['galleryBody']:
            content_html += render_content(content)
        for slide in article_json['slides']:
            for content in slide['mediaContent']:
                content_html += render_content(content)
    else:
        lead_items = None
        if article_json.get('lead'):
            lead_items = article_json['lead']
        elif article_json.get('pageLead'):
            lead_items = article_json['pageLead']
        elif article_json.get('blogLead'):
            lead_items = article_json['blogLead']
        if lead_items:
            if lead_items[0].get('items'):
                lead_items = lead_items[0]['items']
            content_html += render_content(lead_items[0])
            if lead_items[0].get('image'):
                if isinstance(lead_items[0]['image'], dict):
                    item['_image'] = lead_items[0]['image']['src']
                elif isinstance(lead_items[0]['image'], list):
                    item['_image'] = lead_items[0]['image'][0]['image']['src']
            elif lead_items[0].get('thumbnailUrl'):
                item['_image'] = lead_items[0]['thumbnailUrl']
            elif lead_items[0].get('thumbnail'):
                item['_image'] = lead_items[0]['thumbnail'][0]['image']['src']
            else:
                m = re.search(r'<img .*?src="([^"]+)"', content_html)
                if m:
                    item['_image'] = m.group(1)

        if article_json.get('audio'):
            item['attachments'] = []
            for audio in article_json['audio']:
                attachment = {}
                src = next((it for it in audio['sources'] if (it.get('type') and it['type'] == 'audio/mpeg')), None)
                if not src:
                    src = audio['sources'][0]
                if 'podtrac.com' in src['src']:
                    attachment['url'] = utils.get_redirect_url(src['src'])
                else:
                    attachment['url'] = src['src']
                if src.get('type'):
                    attachment['mime_type'] = src['type']
                elif '.mp3' in attachment['url']:
                    attachment['mime_type'] = 'audio/mpeg'
                item['attachments'].append(attachment)
                if 'PodcastEpisodePage.hbs' in article_json['_template']:
                    poster = article_json['podcastImage'][0]['image']['src']
                    poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(poster))
                    content_html += '<table><tr><td><a href="{}"><img src="{}"/></a></td>'.format(attachment['url'], poster)
                    content_html += '<td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold"><a href="{}">{}</a></div>'.format(item['url'], item['title'])
                    content_html += '<div><a href="{}">{}</a></div>'.format(article_json['podcastLink'][0]['href'], article_json['podcastLink'][0]['body'])
                    content_html += '<div style="font-size:0.8em;">{} &bull; {}</div></td></tr></table>'.format(short_display_date, audio['duration'])
                else:
                    content_html += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Listen ({2})</a></span></div><div>&nbsp;</div>'.format(attachment['url'], config.server, audio['duration'])

        if article_json['_template'] == '/liveblog/LiveBlogPage.hbs':
            # https://www.latimes.com/delos/liveblog/latin-grammy-awards-2023-live-updates-from-sevilla
            for content in article_json['blogBody']:
                content_html += render_content(content)
            for content in article_json['currentPosts']:
                content_html += render_content(content)
        elif article_json['_template'] == '/listicle/ListiclePage.hbs':
            # https://www.nbcsports.com/nfl/profootballtalk/fmia/jared-goff-josh-allen-lamar-jackson-joe-burrow-deshaun-watson-brock-purdy-tommy-devito-fmia-week-11-peter-king
            if article_json.get('intro'):
                for content in article_json['intro']:
                    content_html += render_content(content)
            if article_json.get('listicleBody'):
                for content in article_json['listicleBody']:
                    content_html += render_content(content)
            if article_json.get('items'):
                for content in article_json['items']:
                    content_html += render_content(content, True)
            if article_json.get('item'):
                for content in article_json['item']:
                    content_html += render_content(content, True)
        elif article_json['_template'] == '/video/VideoPage.hbs':
            for content in article_json['video']:
                content_html += render_content(content)
        elif article_json.get('articleBody'):
            for content in article_json['articleBody']:
                content_html += render_content(content)
        elif article_json.get('body'):
            for content in article_json['body']:
                content_html += render_content(content)

        if 'PodcastEpisodePage.hbs' in article_json['_template'] and article_json['audio'][0].get('transcripts'):
            content_html += '<div>&nbsp;</div><hr/><div>&nbsp;</div><h3>Transcript</h3>'
            for it in article_json['audio'][0]['transcripts']:
                content_html += render_content(it)

        if lead_items and len(lead_items) > 1:
            content_html += '<h3>Additional media</h3>'
            for it in lead_items[1:]:
                content_html += render_content(it)

    soup = BeautifulSoup(content_html, 'html.parser')
    for el in soup.find_all(class_='twitter-tweet'):
        links = el.find_all('a')
        new_html = utils.add_embed(links[-1]['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        if el.parent and el.parent.name == 'p':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'p':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(class_='dropcap-image'):
        el.decompose()

    for el in soup.find_all('p', attrs={"data-has-dropcap-image": True}):
        el.attrs = {}
        new_html = re.sub(r'>("?\w)', r'><span style="float:left; font-size:4em; line-height:0.8em;">\1</span>', str(el), 1)
        new_html += '<span style="clear:left;"></span>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('script'):
        el.decompose()

    content_html = str(soup)
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', content_html)
    return item


def get_feed(url, args, site_json, save_debug=False):
    if url.endswith('rss') or url.endswith('xml'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    page_json = utils.get_url_json(utils.clean_url(url) + '?_renderer=json')
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/feed.json')

    articles = []
    def iter_module(module):
        nonlocal articles
        if 'AdModule.hbs' in module['_template'] or '/text/RichTextModule.hbs' in module['_template'] or '/htmlmodule/HtmlModule.hbs' in module['_template']:
            return
        elif '/container/Container.hbs' in module['_template']:
            if module.get('rows'):
                for it in module['rows']:
                    iter_module(it)
            if module.get('columns'):
                for it in module['columns']:
                    iter_module(it)
        elif 'ColumnContainer.hbs' in module['_template']:
            if module.get('columnOne'):
                for it in module['columnOne']:
                    iter_module(it)
            if module.get('columnTwo'):
                for it in module['columnTwo']:
                    iter_module(it)
            if module.get('columnThree'):
                for it in module['columnThree']:
                    iter_module(it)
            if module.get('columnFour'):
                for it in module['columnFour']:
                    iter_module(it)
        elif module['_template'] == '/module/Wrapper.hbs':
            for it in module['module']:
                iter_module(it)
        elif module['_template'] == '/hub-hero/HubHero.hbs':
            if module.get('featured'):
                for it in module['featured']:
                    iter_module(it)
            if module.get('leftSidebar'):
                for it in module['leftSidebar']:
                    iter_module(it)
            if module.get('rightSidebar'):
                for it in module['rightSidebar']:
                    iter_module(it)
        elif module['_template'] == '/video/VideoPlaylistModule.hbs':
            for it in module['playlist']:
                iter_module(it)
        elif module['_template'] == '/video/VideoPlaylistItem.hbs':
            for it in module['player']:
                iter_module(it)
        elif module['_template'] == '/mpx/MpxVideoPlayer.hbs':
            if module.get('videoPageUrl') and module['videoPageUrl'] not in articles:
                articles.append(module['videoPageUrl'])
        elif '/list/' in module['_template']:
            for it in module['items']:
                iter_module(it)
        elif '/promo/' in module['_template']:
            if module.get('type') and module['type'] != 'external' and module['type'] != 'oneOffPage' and module['type'] != 'podcast':
                if module['url'] not in articles:
                    articles.append(module['url'])
        else:
            logger.warning('unhandled module template ' + module['_template'])
    for it in page_json['main']:
        iter_module(it)

    n = 0
    feed_items = []
    for url in articles:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['title'] = page_json['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed