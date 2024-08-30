import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from markdown2 import markdown
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_story_content(url, args, site_json, save_debug):
    split_url = urlsplit(url)
    page_html = utils.get_url_html(url)
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    page_soup = BeautifulSoup(page_html, 'lxml')

    item = {}
    item['id'] = split_url.path

    el = page_soup.find('meta', attrs={"property": "og:url"})
    if el:
        item['url'] = el['content']
    else:
        el = page_soup.find('link', attrs={"rel": "canonical"})
        if el:
            item['url'] = el['href']
        else:
            item['url'] = url

    el = page_soup.find('meta', attrs={"property": "og:title"})
    if el:
        item['title'] = el['content']
    else:
        item['title'] = page_soup.title.get_text()

    el = page_soup.find('meta', attrs={"property": "og:image"})
    if el:
        item['_image'] = el['content']
    if '_image' not in item or 'default_fastball_image.jpg' in item['_image']:
        page = page_soup.find('amp-story-page')
        if ':IMAGE:' in page['id']:
            content = page.find('amp-img')
            item['_image'] = content['src']
        elif ':VIDEO:' in page['id']:
            content = page.find('amp-video')
            item['_image'] = content['poster']

    el = page_soup.find('meta', attrs={"property": "og:description"})
    if el and el.get('content'):
        item['summary'] = el['content']

    m = re.search(r'"contentDate":"([^"]+)"', page_html)
    if m:
        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = datetime.fromisoformat(m.group(1))
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)

    item['author'] = {"name": split_url.netloc}

    gallery_url = config.server + '/gallery?url=' + quote_plus(item['url'])
    if 'embed' in args:
        item['content_html'] = '<div style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(split_url.netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}" target="_blank">View story slideshow</a></p></div></div><div>&nbsp;</div>'.format(gallery_url)
        return item

    item['content_html'] = '<h3><a href="{}" target="_blank">View story slideshow</a></h3>'.format(gallery_url)
    item['_gallery'] = []
    for page in page_soup.find_all('amp-story-page'):
        if 'transition-slide' in page['id']:
            continue

        gallery_page = {}
        item['content_html'] += '<div style="min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px;">'

        if page.find(class_=re.compile(r'Typography__Component')):
            has_text = True
        else:
            has_text = False

        if ':IMAGE:' in page['id']:
            content = page.find('amp-img')
            gallery_page['src'] = content['src']
            if content.get('srcset'):
                gallery_page['thumb'] = utils.image_from_srcset(content['srcset'], 640)
            else:
                gallery_page['thumb'] = content['srcset']
            gallery_page['src'] = content['src']
            if has_text:
                item['content_html'] += '<div><img src="{}" style="display:block; width:100%; border-radius:10px 10px 0 0;"/></div>'.format(content['src'])
            else:
                item['content_html'] += '<div><img src="{}" style="display:block; width:100%; border-radius:10px;"/></div>'.format(content['src'])

        if ':VIDEO:' in page['id']:
            content = page.find('amp-video')
            gallery_page['thumb'] = content['poster']
            it = content.find('source', attrs={"type": "video/mp4"})
            gallery_page['src'] = it['src']
            it = content.find('source', attrs={"type": "application/x-mpegURL"})
            if not it:
                it = content.find('source', attrs={"type": "video/mp4"})
            if it:
                poster = '{}/image?url={}&width=540&overlay=video'.format(config.server, quote_plus(content['poster']))
                link = '{}/videojs?src={}&type={}&poster={}'.format(config.server, quote_plus(it['src']), quote_plus(it['type']), quote_plus(content['poster']))
                if has_text:
                    item['content_html'] += '<div><a href="{}"><img src="{}" style="display:block; width:100%; border-radius:10px 10px 0 0;"/></a></div>'.format(link, poster)
                else:
                    item['content_html'] += '<div><a href="{}"><img src="{}" style="display:block; width:100%; border-radius:10px;"/></a></div>'.format(link, poster)

        gallery_desc = ''
        content = page.find_all(class_=re.compile(r'PlayInfo__PlayerSpotContainer'))
        if content:
            gallery_desc += '<div style="margin:0; padding:8px 8px 0 8px;">'
            for el in content:
                for it in el.find_all('amp-img', recursive=False):
                    gallery_desc += '<img src="{}/image?url={}&height=48&width=48&mask=ellipse" title="{}" style="padding-right:4px;"/>'.format(config.server, quote_plus(it['src']), it['alt'])
            gallery_desc += '</div>'

        if has_text:
            gallery_desc += '<div style="margin:0; padding:0 8px 8px 8px;">'

        content = page.find(class_=re.compile(r'PlayInfo__ScoreInfoContainer'))
        if content:
            gallery_desc += '<table>'
            el = content.find(class_=re.compile(r'PlayInfo__Inning'))
            if el:
                gallery_desc += '<tr><td colspan="2">' + el.decode_contents() + '</td></tr>'
            el = content.find(class_=re.compile(r'PlayInfo__TeamScoreContainer'))
            if el:
                for it in el.find_all('span', class_=False):
                    gallery_desc += '<tr style="font-weight:bold;"><td>' + it.get_text() +  '</td><td>' + it.find_next_sibling(class_=re.compile(r'PlayInfo__Score')).get_text() + '</td></tr>'
            el = content.find(class_=re.compile(r'PlayInfo__Result'))
            if el:
                gallery_desc += '<tr><td colspan="2" style="font-size:0.8em;">' + el.decode_contents() + '</td></tr>'
            gallery_desc += '</table>'
            content.decompose()

        content = page.find(class_=re.compile(r'PlayerStats__Container'))
        if content:
            gallery_desc += '<div style="padding-top:8px;">'
            for el in content.find_all(class_=re.compile(r'PlayerStats__StatsContainer')):
                el.attrs = {}
                it = el.find(class_=re.compile(r'PlayerStats__Stat'))
                it.attrs = {}
                gallery_desc += str(el)
            gallery_desc += '</div>'
            content.decompose()

        content = page.find(class_=re.compile(r'Title-'))
        if content:
            el = page.find(class_=re.compile(r'ImpactLabel-'))
            if el:
                gallery_desc += '<div style="padding-top:12px;"><span style="font-weight:bold; color:white; background-color:#444;">' + el.decode_contents() + '</span></div>'
                el.decompose()
                gallery_desc += '<div style="font-size:1.2em; font-weight:bold;">'
            else:
                gallery_desc += '<div style="font-size:1.2em; font-weight:bold; padding-top:12px;">'
            gallery_desc += content.decode_contents() + '</div>'
            content.decompose()

        content = page.find(class_=re.compile(r'PlayInfo__MatchupContainer'))
        if content:
            gallery_desc += '<div style="padding-top:8px;">'
            for el in content.find_all('span'):
                gallery_desc += '<div style="font-weight:bold;">' + el.decode_contents() + '</div>'
            gallery_desc += '</div>'
            content.decompose()

        it = page.find(class_=re.compile(r'Chin-'))
        if it:
            content = it.find_all(class_=re.compile(r'Typography__Component'))
            if content:
                for el in content:
                    if not el.find_parent(class_=re.compile(r'Footer-')):
                        gallery_desc += str(el)

        content = page.find('amp-story-page-outlink')
        if content:
            gallery_desc += utils.add_button(content.a['data-vars-button-link'], content.a['data-vars-button-text'])

        it = page.find(class_=re.compile(r'Footer'))
        if it:
            content = it.find_all(class_=re.compile(r'Typography__Component'))
            if content:
                for el in content:
                    gallery_desc += '<div style="font-size:0.8em; text-align:right;">' + el.decode_contents() + '</div>'
            it.decompose()

        if has_text:
            gallery_desc += '</div>'

        item['content_html'] += gallery_desc + '</div><div>&nbsp;</div>'
        gallery_page['desc'] = gallery_desc
        item['_gallery'].append(gallery_page)
    return item


def get_article(url):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] == 'es':
        language = 'ES_US'
    else:
        language = 'EN_US'
    post_data = {
        "operationName": "GetArticle",
        "variables": {
            "storySlug": paths[-1],
            "forgeLocale": language
        },
        "query": '''
    query GetArticle(
        $forgeLocale: Language
        $formatString: StringFormatDirectiveTypes
        $storySlug: String!
    ) {
        story: getArticle(slug: $storySlug, language: $forgeLocale) {
            translationId
            slug
            byline
            isMigrated
            contentDate
            contributors {
                name
                tagline(formatString: $formatString)
                thumbnail {
                    templateUrl
                }
                twitterHandle
            }
            headline
            lastUpdatedDate
            parts {
                ... on OEmbed {
                    __typename
                    html
                    providerName
                    providerUrl
                    type
                    width
                    contentType
                }
                ... on Markdown {
                    __typename
                    content
                    type
                }
                ... on Image {
                    __typename
                    caption
                    contextualCaption
                    contextualAspectRatio
                    credit
                    contentType
                    format
                    templateUrl
                    type
                }
                ... on PullQuote {
                    __typename
                    author
                    quote
                    type
                }
                ... on Video {
                    __typename
                    contentDate
                    mp4AvcPlayback: preferredPlaybackScenarioURL(
                        preferredPlaybacks: "mp4AvcPlayback"
                    )
                    type
                    description
                    displayAsVideoGif
                    duration
                    slug
                    tags {
                        ... on ContributorTag {
                            slug
                            type
                        }
                        ... on InternalTag {
                            slug
                            title
                            type
                        }
                        ... on PersonTag {
                            slug
                            title
                            person {
                                id
                            }
                            type
                        }
                        ... on TaxonomyTag {
                            slug
                            title
                            type
                        }
                        ... on TeamTag {
                            slug
                            title
                            team {
                                id
                            }
                            type
                        }
                    }
                    thumbnail {
                        templateUrl
                    }
                    title
                    url: relativeSiteUrl
                }
            }
            relativeSiteUrl
            storyType: contentType
            subHeadline
            summary
            tagline(formatString: $formatString)
            tags {
                ... on ContributorTag {
                    slug
                    title
                    type
                }
                ... on GameTag {
                    slug
                    title
                    type
                }
                ... on InternalTag {
                    slug
                    title
                    type
                }
                ... on PersonTag {
                    slug
                    title
                    person {
                        id
                    }
                    type
                }
                ... on TaxonomyTag {
                    slug
                    title
                    type
                }
                ... on TeamTag {
                    slug
                    title
                    team {
                        id
                    }
                    type
                }
            }
            type
            templateUrl: thumbnail
            title
        }
    }
        '''
    }
    article_json = utils.post_url('https://data-graph.mlb.com/graphql', json_data=post_data)
    if not article_json:
        return None
    return article_json['data']['story']


def get_video_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    video_url = 'https://' + split_url.netloc + '/data-service/en/videos/' + paths[-1]
    video_json = utils.get_url_json(video_url)
    if not video_json:
        return None
    if save_debug:
        utils.write_file(video_json, './debug/debug.json')

    item = {}
    item['id'] = video_json['id']
    item['url'] = 'https://' + split_url.netloc + '/video/' + video_json['slug']
    item['title'] = video_json['title']

    dt = datetime.fromisoformat(video_json['date'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": split_url.netloc}

    if video_json.get('keywordsDisplay'):
        item['tags'] = []
        for it in video_json['keywordsDisplay']:
            item['tags'].append(it['displayName'])

    if video_json.get('description'):
        item['summary'] = video_json['description']
    elif video_json.get('blurb'):
        item['summary'] = video_json['blurb']

    if 'templateUrl' in video_json['image']:
        item['_image'] = video_json['image']['templateUrl'].replace('{formatInstructions}', 't_16x9/t_w1024')
    else:
        image = utils.closest_dict(video_json['image']['cuts'], 'width', 1200)
        if image:
            item['_image'] = image['src']

    item['content_html'] = ''
    video = next((it for it in video_json['playbacks'] if it['name'] == 'hlsCloud'), None)
    if video:
        item['_video'] = video['url']
        item['_video_type'] = 'application/x-mpegURL'
    else:
        video = next((it for it in video_json['playbacks'] if it['name'] == 'mp4Avc'), None)
        if video:
            item['_video'] = video['url']
            item['_video_type'] = 'video/mp4'
    if video:
        item['content_html'] += utils.add_video(item['_video'], item['_video_type'], item['_image'], item['title'])

    if 'embed' not in args and 'summary' in item:
        item['content_html'] += '<p>' + item['summary'] + '</p>'
    return item


def get_news_forge_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    page_soup = BeautifulSoup(page_html, 'lxml')
    el = page_soup.find('div', class_='article-data')
    if el:
        article_json = json.loads(el['data-article-json'])
        if save_debug:
            utils.write_file(article_json, './debug/debug.json')

    # article_body = utils.get_url_html(url.replace('/news/', '/news-forge/article-body/'))
    # article_data = utils.get_url_json(url.replace('/news/', '/news-forge/article-data/'))

    item = {}
    item['id'] = article_json['slug']
    item['url'] = 'https://' + split_url.netloc + article_json['canonical']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['contentDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if article_json.get('byline') and 'name' in article_json['byline']:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(article_json['byline']['name']))
    else:
        item['author'] = {"name": split_url.netloc}

    if article_json.get('tags'):
        item['tags'] = []
        for val in article_json['tags'].values():
            for it in val:
                item['tags'].append(it['title'])

    if article_json.get('teaser'):
        item['summary'] = article_json['teaser']

    item['content_html'] = ''
    if article_json.get('subHeadline'):
        item['content_html'] += '<p><em>' + article_json['subHeadline'] + '</em></p>'

    if article_json.get('thumbnail'):
        item['_image'] = article_json['thumbnail']['src']

    if article_json.get('media'):
        if article_json['media']['type'] == 'photo':
            image = utils.closest_dict(article_json['media']['content']['cuts'], 'width', 1200)
            captions = []
            if article_json['media'].get('caption'):
                captions.append(article_json['media']['caption'])
            if article_json['media'].get('credit'):
                captions.append(article_json['media']['credit'])
            item['content_html'] += utils.add_image(image['src'], ' | '.join(captions))
        elif article_json['media']['type'] == 'video':
            video_url = 'https://' + split_url.netloc + '/video/' + article_json['media']['video']['slug']
            video_item = get_video_content(video_url, {"embed": True}, site_json, False)
            if video_item:
                item['content_html'] += video_item['content_html']
    elif '_image' in item:
        item['content_html'] += utils.add_image(item['_image'])

    for part in article_json['articleParts']:
        if part['type'] == 'markdown':
            item['content_html'] += part['content']
        elif part['type'] == 'photo':
            image = utils.closest_dict(part['content']['cuts'], 'width', 1200)
            captions = []
            if part.get('caption'):
                captions.append(part['caption'])
            if part.get('credit'):
                captions.append(part['credit'])
            item['content_html'] += utils.add_image(image['src'], ' | '.join(captions))
        elif part['type'] == 'video':
            video_url = 'https://' + split_url.netloc + '/video/' + part['media']['video']['slug']
            video_item = get_video_content(video_url, {"embed": True}, site_json, False)
            if video_item:
                item['content_html'] += video_item['content_html']
        elif part['type'] == 'external' and part['content'].startswith('<iframe'):
            m = re.search(r'src="([^"]+)"', part['content'])
            if m:
                item['content_html'] += utils.add_embed(m.group(1))
        elif part['type'] == 'external' and 'provider' in part and part['provider'] == 'Twitter':
            m = re.findall(r'href="([^"]+)"', part['content'])
            if m:
                item['content_html'] += utils.add_embed(m[-1])
        else:
            logger.warning('unhandled article part type {} in {}'.format(part['type'], item['url']))

    item['content_html'] += re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_content(url, args, site_json, save_debug=False):
    if '/stories/' in url:
        return get_story_content(url, args, site_json, save_debug)

    if '/video/' in url:
        return get_video_content(url, args, site_json, save_debug)

    if '/news/' in url and 'www.milb.com' in url:
        return get_news_forge_content(url, args, site_json, save_debug)

    if '/news/' not in url:
        logger.warning('unhandled url ' + url)
        return None

    article_json = get_article(url)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['translationId']
    item['url'] = url
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['contentDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['lastUpdatedDate'])
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('contributors'):
        authors = []
        for it in article_json['contributors']:
            authors.append(it['name'])
        if authors:
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json.get('byline'):
        item['author']['name'] = article_json['byline']
    else:
        item['author']['name'] = urlsplit(url).netloc

    if article_json.get('tags'):
        item['tags'] = []
        for it in article_json['tags']:
            if it['type'] == 'contributor' or it['type'] == 'article':
                continue
            item['tags'].append(it['title'])
        if not item.get('tags'):
            del item['tags']

    if article_json.get('templateUrl'):
        item['_image'] = article_json['templateUrl'].replace('{formatInstructions}', 't_16x9/t_w1024')

    if article_json.get('summary'):
        item['summary'] = article_json['summary']

    if 'embed' in args:
        item['content_html'] = '<div style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(urlsplit(item['url']).netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}" target="_blank">Read</a></p></div></div><div>&nbsp;</div>'.format(config.server, quote_plus(item['url']))
        return item

    item['content_html'] = ''
    if article_json.get('subHeadline'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['subHeadline'])

    for part in article_json['parts']:
        if '__typename' not in part:
            continue
        elif part['__typename'] == 'Markdown':
            content = markdown(part['content'].replace(' >', '>'))
            #content = '<p>{}</p>'.format(part['content'].replace('\n\n', '</p><p>').replace('\\', ''))
            soup = BeautifulSoup(content, 'html.parser')
            for el in soup.find_all('forge-entity'):
                new_html = ''
                if el['code'] == 'player':
                    new_html = '<a href="https://www.mlb.com/player/{}">{}</a>'.format(el['slug'].split('-')[-1], el.get_text())
                if new_html:
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()
                else:
                    logger.warning('unhandled forge-entity code {} in {}'.format(el['code'], item['url']))
            item['content_html'] += str(soup)

        elif part['__typename'] == 'Image':
            img_src = part['templateUrl'].replace('{formatInstructions}', 't_16x9/t_w1024')
            captions = []
            if part.get('contextualCaption'):
                captions.append(part['contextualCaption'])
            elif part.get('caption'):
                captions.append(part['caption'])
            if part.get('credit'):
                captions.append(part['credit'])
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))

        elif part['__typename'] == 'Video':
            img_src = part['thumbnail']['templateUrl'].replace('{formatInstructions}', 't_16x9/t_w1024')
            if part.get('description'):
                caption = part['description']
            elif part.get('title'):
                caption = part['title']
            else:
                caption = ''
            m = re.search(r'-asset.*?\.mp4', part['mp4AvcPlayback'])
            if m:
                item['content_html'] += utils.add_video(part['mp4AvcPlayback'].replace(m.group(0), '-asset.m3u8'), 'application/x-mpegurl', img_src, caption)
            else:
                item['content_html'] += utils.add_video(part['mp4AvcPlayback'], 'video/mp4', img_src, caption)

        elif part['__typename'] == 'OEmbed':
            if part['providerName'] == 'Twitter':
                soup = BeautifulSoup(part['html'], 'html.parser')
                links = soup.find_all('a')
                item['content_html'] += utils.add_embed(links[-1]['href'])
            elif part['providerName'] == 'MLB' and 'story-player-iframe' in part['html']:
                m = re.search(r'src="([^"]+)"', part['html'])
                item['content_html'] += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled oembed provider {} in {}'.format(part['providerName'], item['url']))

        else:
            logger.warning('unhandled content part type {} in {}'.format(part['__typename'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
