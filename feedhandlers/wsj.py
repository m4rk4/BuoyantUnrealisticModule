import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


# Testing:
# media-object-podcast: https://www.wsj.com/amp/articles/taliban-seize-kandahar-prepare-to-march-on-kabul-11628846975

def get_caption(el):
    caption = []
    img_caption = el.find(class_=re.compile(r'imageCaption\b|wsj-article-caption'))
    if img_caption:
        txt = img_caption.get_text().strip()
        if txt:
            caption.append(txt)
    else:
        img_caption = el.find(class_='imageCaptionContent')
        if img_caption:
            txt = img_caption.get_text().strip()
            if txt:
                caption.append(txt)
        img_credit = el.find(class_='imageCredit')
        if img_credit:
            txt = img_credit.get_text().strip()
            if txt:
                caption.append(txt)
    return ' | '.join(caption)


def convert_amp_image(el):
    img = el.find('amp-img')
    if img:
        if img.has_attr('srcset'):
            img_src = utils.image_from_srcset(img['srcset'], 1000)
        else:
            img_src = img['src']
        return utils.add_image(img_src, get_caption(el))
    return ''


def convert_amp_video(iframe, src='', caption=''):
    video_html = ''
    if iframe:
        src = iframe.find('amp-iframe').get('src')
    m = re.search(r'guid=([0-9A-F\-]+)', src)
    if m:
        api_url = 'https://video-api.shdsvc.dowjones.io/api/legacy/find-all-videos?type=guid&count=1&https=1&query={}&fields=isQAEvent,type,video174kMP4Url,video320kMP4Url,video664kMP4Url,video1264kMP4Url,video1864kMP4Url,video2564kMP4Url,hls,videoMP4List,adZone,thumbnailList,guid,state,secondsUntilStartTime,author,description,name,linkURL,videoStillURL,duration,videoURL,adCategory,adsAllowed,chapterTimes,catastrophic,linkShortURL,doctypeID,youtubeID,titletag,rssURL,wsj-section,wsj-subsection,allthingsd-section,allthingsd-subsection,sm-section,sm-subsection,provider,formattedCreationDate,iso8601CreationDate,keywords,keywordsOmni,column,editor,emailURL,emailPartnerID,showName,omniProgramName,omniVideoFormat,linkRelativeURL,touchCastID,omniPublishDate,adTagParams,gptCustParams,format,forceClosedCaptions,captionsVTT,hlsNoCaptions,episodeNumber,seriesName,thumbstripURL,thumbnailImageManager,ads_allowed,mediaLiveChannelId'.format(
            m.group(1))
        video_json = utils.get_url_json(api_url)
        if video_json:
            if True:
                utils.write_file(video_json, './debug/video.json')
            video_src = utils.closest_dict(video_json['items'][0]['videoMP4List'], 'height', 480)
            poster = utils.closest_dict(video_json['items'][0]['thumbnailList'], 'width', 1000)
            if iframe:
                caption = get_caption(iframe)
            video_html = utils.add_video(video_src['url'], 'video/mp4', poster['url'], caption)
    return video_html


def get_video_content(url, args, save_debug=False):
    article_html = utils.get_url_html(url, 'googlebot')
    if not article_html:
        return None
    if save_debug:
        with open('./debug/debug.html', 'w', encoding='utf-8') as f:
            f.write(article_html)

    soup = BeautifulSoup(article_html, 'html.parser')

    item = {}
    el = soup.find('script', attrs={"type": "application/ld+json"})
    if el:
        ld_json = json.loads(el.string)
        m = re.search(r'guid=([0-9A-Fa-f\-]+)', ld_json['embedUrl'])
        if m:
            api_url = 'https://video-api.shdsvc.dowjones.io/api/legacy/find-all-videos?type=guid&count=1&https=1&query={}&fields=isQAEvent,type,video174kMP4Url,video320kMP4Url,video664kMP4Url,video1264kMP4Url,video1864kMP4Url,video2564kMP4Url,hls,videoMP4List,adZone,thumbnailList,guid,state,secondsUntilStartTime,author,description,name,linkURL,videoStillURL,duration,videoURL,adCategory,adsAllowed,chapterTimes,catastrophic,linkShortURL,doctypeID,youtubeID,titletag,rssURL,wsj-section,wsj-subsection,allthingsd-section,allthingsd-subsection,sm-section,sm-subsection,provider,formattedCreationDate,iso8601CreationDate,keywords,keywordsOmni,column,editor,emailURL,emailPartnerID,showName,omniProgramName,omniVideoFormat,linkRelativeURL,touchCastID,omniPublishDate,adTagParams,gptCustParams,format,forceClosedCaptions,captionsVTT,hlsNoCaptions,episodeNumber,seriesName,thumbstripURL,thumbnailImageManager,ads_allowed,mediaLiveChannelId'.format(
                m.group(1))
            video_json = utils.get_url_json(api_url)
            if video_json:
                if save_debug:
                    utils.write_file(video_json, './debug/video.json')
                item['id'] = video_json['items'][0]['guid']
                item['url'] = url
                item['title'] = video_json['items'][0]['name']
                dt_pub = datetime.fromisoformat(video_json['items'][0]['iso8601CreationDate'].replace('Z', '+00:00'))
                item['date_published'] = dt_pub.isoformat()
                item['_timestamp'] = dt_pub.timestamp()
                item['_display_date'] = dt_pub.strftime('%b %-d, %Y')
                item['author'] = {}
                item['author']['name'] = video_json['items'][0]['author']
                item['tags'] = [tag.title() for tag in video_json['items'][0]['keywords']]

                poster = utils.closest_dict(video_json['items'][0]['thumbnailList'], 'width', 1000)
                item['_image'] = poster['url']

                item['summary'] = video_json['items'][0]['description']

                video_src = utils.closest_dict(video_json['items'][0]['videoMP4List'], 'height', 480)
                item['content_html'] = utils.add_video(video_src['url'], 'video/mp4', poster['url'])
                item['content_html'] += '<h4>{}</h4><p>{}</p>'.format(video_json['items'][0]['titletag'],
                                                                      video_json['items'][0]['description'])
        return item


def get_story_content(url, args, save_debug=False):
    article_html = utils.get_url_html(url, 'googlebot')
    if not article_html:
        return None
    if save_debug:
        with open('./debug/debug.html', 'w', encoding='utf-8') as f:
            f.write(article_html)

    soup = BeautifulSoup(article_html, 'html.parser')

    item = {}
    el = soup.find('script', attrs={"type": "application/ld+json"})
    if el:
        ld_json = json.loads(el.string)
        item['id'] = soup.find('meta', attrs={"name": "page.id"}).get('content')
        item['url'] = url
        item['title'] = ld_json['headline']
        dt_pub = datetime.fromisoformat(ld_json['dateCreated'].replace('Z', '+00:00'))
        item['date_published'] = dt_pub.isoformat()
        dt_mod = datetime.fromisoformat(ld_json['dateModified'].replace('Z', '+00:00'))
        item['date_modified'] = dt_mod.isoformat()
        item['_timestamp'] = dt_pub.timestamp()
        item['_display_date'] = dt_pub.strftime('%b %-d, %Y')
        el = soup.find(class_='wsj--byline')
        if el:
            byline = el.get_text()
            item['author'] = {}
            if byline.startswith('By '):
                item['author']['name'] = byline[3:]
            else:
                item['author']['name'] = byline
        item['_image'] = ld_json['image'][0]['url']
        item['summary'] = ld_json['description']

        content_html = ''
        for page in soup.find_all('amp-story-page'):
            if 'wsj--cover-slide' in page['class'] or 'wsj--image-slide' in page['class']:
                img = page.find('amp-img')
                el = page.find(class_='wsj--credit')
                if el:
                    content_html += utils.add_image(img['src'], el.get_text())
                else:
                    content_html += utils.add_image(img['src'])
                el = page.find(class_='wsj--title')
                if el:
                    content_html += '<h3>{}</h3>'.format(el.get_text())
                el = page.find(class_='wsj--caption')
                if el:
                    content_html += '<p>{}<p>'.format(el.get_text())
                el = page.find(class_='wsj--description')
                if el:
                    content_html += '<p>{}<p>'.format(el.get_text())
            elif 'wsj--text-slide' in page['class']:
                el = page.find(class_='wsj--title')
                if el:
                    content_html += '<h3>{}</h3>'.format(el.get_text())
                for el in page.find_all('p'):
                    content_html += str(el)
            else:
                logger.warning('unhandled amp-story-page type in ' + url)
                content_html += '<i>unhandled amp-story-page type</i>'
            content_html += '<hr width="60%" />'
        item['content_html'] = content_html
    return item


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    clean_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)
    if '/video/' in clean_url:
        return get_video_content(clean_url, args, save_debug)
    elif '/story/' in clean_url:
        return get_story_content(clean_url, args, save_debug)

    if split_url.path.startswith('/amp/'):
        amp_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)
    else:
        amp_url = '{}://{}/amp{}'.format(split_url.scheme, split_url.netloc, split_url.path)
    article_html = utils.get_url_html(amp_url, 'googlebot')
    if not article_html:
        return None
    if save_debug:
        with open('./debug/debug.html', 'w', encoding='utf-8') as f:
            f.write(article_html)

    soup = BeautifulSoup(article_html, 'html.parser')

    item = {}
    item['id'] = soup.find('meta', attrs={"name": "article.id"}).get('content')
    item['url'] = clean_url
    item['title'] = soup.find('meta', attrs={"name": "article.headline"}).get('content')

    dt = datetime.fromisoformat(
        soup.find('meta', attrs={"itemprop": "datePublished"}).get('content').replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    dt = datetime.fromisoformat(
        soup.find('meta', attrs={"itemprop": "dateModified"}).get('content').replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    author = soup.find('meta', attrs={"name": "author"})
    if author:
        item['author']['name'] = author.get('content')
    elif soup.find('meta', attrs={"name": "article.type"}).get('content') == 'Letters':
        item['author']['name'] = 'WSJ Letters'
    else:
        item['author']['name'] = 'WSJ'

    item['tags'] = soup.find('meta', attrs={"name": "news_keywords"}).get('content').split(',')

    item['_image'] = soup.find('meta', attrs={"itemprop": "image"}).get('content')
    item['summary'] = soup.find('meta', attrs={"name": "article.summary"}).get('content')

    content_html = ''
    lead = ''
    el = soup.find(class_=re.compile(r'articleLead|bigTop-hero'))
    if el:
        if el.find(class_='media-object-video'):
            lead = convert_amp_video(el)
        else:  # media-object-image
            lead = convert_amp_image(el)
    if lead:
        content_html += lead
    else:
        if item.get('_image'):
            content_html += utils.add_image(item['_image'])

    article_body = soup.find(class_="articleBody")
    if not article_body:
        article_body = soup.find(class_="article__body")
        if not article_body:
            logger.warning('unable to find article body in ' + clean_url)
            return item

    article = article_body.find('section', attrs={"subscriptions-section": "content"})
    if not article:
        article = article_body.find(attrs={"amp-access": "access", "class": False})

    el = article.find(class_='paywall')
    if el:
        el.unwrap()

    for el in article.find_all(class_='wsj-ad'):
        el.decompose()

    for el in article.find_all('h6'):
        el.name = 'h3'

    for el in article.find_all(class_='media-object'):
        new_html = ''
        if not list(filter(re.compile(r'scope-web').search, el['class'])):
            el.decompose()

        elif re.search(r'From the Archives|Newsletter Sign-Up|SHARE YOUR THOUGHTS', el.get_text(), flags=re.I) or len(
                el.contents) == 1:
            el.decompose()

        elif 'smallrule' in el['class']:
            new_html = '<hr width="60%" />'

        elif el.find(class_='wsj-article-pullquote'):
            quote = el.find(class_='pullquote-content').get_text()
            m = re.search(r'^[^\w]*(\w.*?)[^\w\.]*$', quote)
            if m:
                quote = m.group(1)
            new_html = utils.add_pullquote(quote)

        elif el.find(class_='media-object-image'):
            new_html = convert_amp_image(el)

        elif el.find(class_='media-object-slideshow'):
            new_html = ''
            it = el.find(class_='wsj-slideshow-title')
            if it:
                new_html += '<h3>Slideshow: {}</h3>'.format(it.get_text())
            it = el.find(class_='wsj-media-dek')
            if it:
                new_html += '<p>{}</p>'.format(it.get_text())
            for it in el.find_all(class_='media-object-slideshow-slide'):
                new_html += convert_amp_image(it) + '<br/>'

        elif el.find(class_='media-object-video'):
            new_html = convert_amp_video(el)

        elif el.find(class_='media-object-interactiveLink'):
            new_html = '<hr width="60%" /><h4>{}</h4>'.format(str(el.a))
            new_html += convert_amp_image(el)
            new_html += '<hr width="60%" />'

        elif el.find(class_='media-object-podcast'):
            iframe_src = el.find('amp-iframe').get('src')
            m = re.search(r'guid=([0-9A-Fa-f\-]+)', iframe_src)
            if m:
                api_url = 'https://video-api.shdsvc.dowjones.io/api/legacy/find-all-videos?type=guid&query={}&fields=adZone,allthingsd-section,allthingsd-subsection,audioURL,audioURLPanoply,author,column,description,doctypeID,duration,episodeNumber,formattedCreationDate,guid,keywords,linkURL,name,omniPublishDate,omniVideoFormat,playbackSite,podcastName,podcastSubscribeLinks,podcastUrl,sm-section,sm-subsection,thumbnailImageManager,thumbnailList,thumbnailUrl,titletag,type,wsj-section,wsj-subsection'.format(
                    m.group(1))
                if True:
                    logger.debug('getting podcast details from ' + api_url)
                podcast_json = utils.get_url_json(api_url)
                if podcast_json and not podcast_json['items'][0].get('error'):
                    img_src = podcast_json['items'][0]['thumbnailImageManager'] + '?height=96'
                    poster = '{}/image?url={}&overlay=audio'.format(config.server, quote_plus(img_src))
                    desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4>by <a href="{}">{}</a>'.format(
                        podcast_json['items'][0]['linkURL'], podcast_json['items'][0]['name'],
                        podcast_json['items'][0]['podcastUrl'], podcast_json['items'][0]['podcastName'])
                    new_html = '<div><a href="{}"><img style="float:left; margin-right:8px; height:128px;" src="{}"/></a><div style="overflow:auto; display:block;">{}</div><div style="clear:left;"></div>'.format(
                        podcast_json['items'][0]['audioURL'], poster, desc)
                    new_html += '<blockquote style="border-left:3px solid #ccc; margin-top:4px; margin-left:1.5em; padding-left:0.5em;"><small>{}</small></blockquote></div>'.format(
                        podcast_json['items'][0]['description'].replace('\n', '<br/>'))

        elif el.find(class_='media-object-rich-text'):
            if el.ul:
                # Usually a list of articles
                el.ul.parent.unwrap()
                el.unwrap()
            elif el.h4:
                # Usually a read more link
                el.h4.parent.unwrap()
                el.unwrap()
            else:
                logger.warning('unhandled media-object-rich-text in ' + clean_url)

        elif el.find('amp-twitter'):
            it = el.find('amp-twitter')
            tweet = utils.add_twitter(it['data-tweetid'])
            if tweet:
                new_html = tweet
            else:
                logger.warning('unable to get tweet {} in {}'.format(it['data-tweetid'], clean_url))

        elif el.find(class_='dynamic-inset-iframe'):
            iframe_src = el.find('amp-iframe').get('src')
            m = re.search(r'\?url=(.+)$', iframe_src)
            if m:
                url_json = utils.get_url_json(m.group(1))
                if url_json:
                    new_html = ''
                    if url_json.get('subType'):
                        if url_json['subType'] == 'origami':
                            logger.debug('WSJ iframe origami in ' + m.group(1))
                            group_caption = ''
                            n = len(url_json['serverside']['data']['data']['data']['children']) - 1
                            for i, it in enumerate(url_json['serverside']['data']['data']['data']['children']):
                                if it['sub_type'] == 'Origami Photo':
                                    caption = ''
                                    if it['json'].get('caption'):
                                        if url_json['serverside']['data']['data']['data']['json']['groupedCaption'] == True:
                                            group_caption += it['json']['caption']
                                        else:
                                            caption += it['json']['caption']
                                    if it['json'].get('credit'):
                                        if url_json['serverside']['data']['data']['data']['json']['groupedCredit'] == True:
                                            group_caption += it['json']['credit']
                                        else:
                                            caption += it['json']['credit']
                                    if i == n and group_caption:
                                        if caption:
                                            group_caption = caption + '<br />' + group_caption
                                        new_html += utils.add_image(it['json']['media'], group_caption) + '<br/>'
                                    else:
                                        new_html += utils.add_image(it['json']['media'], caption) + '<br/>'

                        elif url_json['subType'] == 'parallax-gallery':
                            for it in url_json['serverside']['data']['data']['items']:
                                if it['type'] == 'image':
                                    caption = it['data'].get('mediaBody')
                                    if caption and caption.startswith('<p>'):
                                        caption = caption[3:-4]
                                    if it['data'].get('mediaCredit'):
                                        caption += ' | ' + it['data']['mediaCredit']
                                    new_html += utils.add_image(it['data']['media'], caption) + '<br/>'
                                else:
                                    logger.warning('unhandled paralax-gallery item in ' + m.group(1))

                        elif url_json['subType'] == 'series-navigation':
                            new_html = '<h4>{}</h4><ul>'.format(url_json['serverside']['data']['data']['data']['title'])
                            for it in url_json['serverside']['data']['data']['items']:
                                new_html += '<li><a href="{}">{}</a></li>'.format(it['link'], it['title'])
                            new_html += '</ul>'

                        elif url_json['subType'] == 'audio-pullquote':
                            new_html = utils.add_pullquote(url_json['serverside']['data']['data']['quoteText'])

                        else:
                            logger.warning('unhandled dynamic-inset-iframe subtype {} in {}'.format(url_json['subType'],
                                                                                                    clean_url))

                    elif url_json.get('type'):
                        logger.warning(
                            'unhandled dynamic-inset-iframe type {} in {}'.format(url_json['type'], clean_url))

                    else:
                        logger.warning('unhandled dynamic-inset-iframe {} in {}'.format(m.group(1), clean_url))

        elif el.find(class_='dynamic-inset-fallback'):
            if el.find('amp-img'):
                new_html = convert_amp_image(el)
            else:
                logger.warning('unhandled dynamic-inset-fallback in ' + clean_url)

        else:
            it = el.find(class_=re.compile(r'media-object-'))
            if it:
                logger.warning('unhandled media-object {} in {}'.format(it['class'], clean_url))
            else:
                logger.warning('unhandled media-object in ' + clean_url)

        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    content_html += str(article)

    item['content_html'] = content_html
    return item


def get_feed(args, save_debug=False):
    if args['url'].endswith('.xml'):
        return rss.get_feed(args, save_debug, get_content)
    # https://www.wsj.com/?id=%7B%22count%22%3A20%2C%22query%22%3A%7B%22and%22%3A%5B%7B%22group%22%3A%7B%22name%22%3A%22WSJ%22%7D%7D%2C%7B%22term%22%3A%7B%22key%22%3A%22SectionType%22%2C%22value%22%3A%22Personal%20Technology%3A%20Joanna%20Stern%22%7D%7D%5D%7D%2C%22sort%22%3A%5B%7B%22key%22%3A%22liveDate%22%2C%22order%22%3A%22desc%22%7D%5D%7D%2Fpage%3D0&type=allesseh_content_full
    # https://www.wsj.com/?id=%7B%22count%22%3A10%2C%22query%22%3A%7B%22and%22%3A%5B%7B%22term%22%3A%7B%22key%22%3A%22AuthorId%22%2C%22value%22%3A%227867%22%7D%7D%2C%7B%22terms%22%3A%7B%22key%22%3A%22Product%22%2C%22value%22%3A%5B%22WSJ.com%22%2C%22WSJPRO%22%5D%7D%7D%5D%7D%2C%22sort%22%3A%5B%7B%22key%22%3A%22LiveDate%22%2C%22order%22%3A%22desc%22%7D%5D%7D%2Fpage%3D0&type=allesseh_content_full

    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 2:
        articles = utils.get_url_json('https://www.wsj.com/?id=%7B%22count%22%3A20%2C%22query%22%3A%7B%22and%22%3A%5B%7B%22group%22%3A%7B%22name%22%3A%22WSJ%22%7D%7D%2C%7B%22term%22%3A%7B%22key%22%3A%22SectionName%22%2C%22value%22%3A%22{}%22%7D%7D%5D%7D%2C%22sort%22%3A%5B%7B%22key%22%3A%22liveDate%22%2C%22order%22%3A%22desc%22%7D%5D%7D%2Fpage%3D0&type=allesseh_content_full'.format(paths[1]))

    elif len(paths) == 3:
        if paths[1] == 'author':
            author = utils.get_url_json('https://www.wsj.com/?id={}&type=author'.format(paths[2]))
            if not author:
                return None
            articles = utils.get_url_json('https://www.wsj.com/?id=%7B%22count%22%3A10%2C%22query%22%3A%7B%22and%22%3A%5B%7B%22term%22%3A%7B%22key%22%3A%22AuthorId%22%2C%22value%22%3A%22{}%22%7D%7D%2C%7B%22terms%22%3A%7B%22key%22%3A%22Product%22%2C%22value%22%3A%5B%22WSJ.com%22%2C%22WSJPRO%22%5D%7D%7D%5D%7D%2C%22sort%22%3A%5B%7B%22key%22%3A%22LiveDate%22%2C%22order%22%3A%22desc%22%7D%5D%7D%2Fpage%3D0&type=allesseh_content_full'.format(author['data']['authorId']))

    if not articles:
        return None
    if save_debug:
        utils.write_file(articles, './debug/feed.json')

    n = 0
    items = []
    for article in articles['collection']:
        article_json = utils.get_url_json('https://www.wsj.com/?id={}&type=article%7Ccapi'.format(article['id']))
        if not article_json:
            logger.warning('error getting article info for ' + article['id'])
        if article_json['data']['articleType'] == 'Photos' or article_json['data']['articleType'] == 'Graphics':
            logger.warning('skipping ' + article_json['data']['url'])
            continue
        if save_debug:
            #utils.write_file(article_json, './debug/debug.json')
            logger.debug('getting content for ' + article_json['data']['url'])
        item = get_content(article_json['data']['url'], args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['items'] = items.copy()
    return feed
