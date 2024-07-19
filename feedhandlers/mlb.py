import pytz, re
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

    item['author'] = {"name": "MLB.com"}

    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(split_url.netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
        return item

    item['content_html'] = ''
    for page in page_soup.find_all('amp-story-page'):
        if 'transition-slide' in page['id']:
            continue
        item['content_html'] += '<table style="min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border-collapse:collapse; border-style:hidden; border-radius:10px; box-shadow:0 0 0 1px black;">'
        # content = page.find(class_=re.compile(r'CoverPanel__PositionTopImage'))
        # if content:
        #     item['content_html'] += '<tr><td style="margin:0; padding:0;"><img src="{}" style="display:block; width:100%; border-radius:10px 10px 0 0;"/></td></tr>'.format(content['src'])

        if page.find(class_=re.compile(r'Typography__Component')):
            has_text = True
        else:
            has_text = False

        if ':IMAGE:' in page['id']:
            content = page.find('amp-img')
            if has_text:
                item['content_html'] += '<tr><td style="margin:0; padding:0;"><img src="{}" style="display:block; width:100%; border-radius:10px 10px 0 0;"/></td></tr>'.format(content['src'])
            else:
                item['content_html'] += '<tr><td style="margin:0; padding:0;"><img src="{}" style="display:block; width:100%; border-radius:10px;"/></td></tr>'.format(content['src'])

        if ':VIDEO:' in page['id']:
            content = page.find('amp-video')
            it = content.find('source', attrs={"type": "application/x-mpegURL"})
            if not it:
                it = content.find('source', attrs={"type": "video/mp4"})
            if it:
                poster = '{}/image?url={}&width=540&overlay=video'.format(config.server, quote_plus(content['poster']))
                link = '{}/videojs?src={}&type={}&poster={}'.format(config.server, quote_plus(it['src']), quote_plus(it['type']), quote_plus(content['poster']))
                if has_text:
                    item['content_html'] += '<tr><td style="margin:0; padding:0;"><a href="{}"><img src="{}" style="display:block; width:100%; border-radius:10px 10px 0 0;"/></a></td></tr>'.format(link, poster)
                else:
                    item['content_html'] += '<tr><td style="margin:0; padding:0;"><a href="{}"><img src="{}" style="display:block; width:100%; border-radius:10px;"/></a></td></tr>'.format(link, poster)

        content = page.find_all(class_=re.compile(r'PlayInfo__PlayerSpotContainer'))
        if content:
            item['content_html'] += '<tr><td style="margin:0; padding:8px 8px 0 8px;">'
            for el in content:
                for it in el.find_all('amp-img', recursive=False):
                    item['content_html'] += '<img src="{}/image?url={}&height=48&width=48&mask=ellipse" title="{}" style="padding-right:4px;"/>'.format(config.server, quote_plus(it['src']), it['alt'])
            item['content_html'] += '</td></tr>'

        if has_text:
            item['content_html'] += '<tr><td style="margin:0; padding:0 8px 8px 8px;">'

        content = page.find(class_=re.compile(r'PlayInfo__ScoreInfoContainer'))
        if content:
            item['content_html'] += '<table>'
            el = content.find(class_=re.compile(r'PlayInfo__Inning'))
            if el:
                item['content_html'] += '<tr><td colspan="2">' + el.decode_contents() + '</td></tr>'
            el = content.find(class_=re.compile(r'PlayInfo__TeamScoreContainer'))
            if el:
                for it in el.find_all('span', class_=False):
                    item['content_html'] += '<tr style="font-weight:bold;"><td>' + it.get_text() +  '</td><td>' + it.find_next_sibling(class_=re.compile(r'PlayInfo__Score')).get_text() + '</td></tr>'
            el = content.find(class_=re.compile(r'PlayInfo__Result'))
            if el:
                item['content_html'] += '<tr><td colspan="2" style="font-size:0.8em;">' + el.decode_contents() + '</td></tr>'
            item['content_html'] += '</table>'
            content.decompose()

        content = page.find(class_=re.compile(r'PlayerStats__Container'))
        if content:
            item['content_html'] += '<div style="padding-top:8px;">'
            for el in content.find_all(class_=re.compile(r'PlayerStats__StatsContainer')):
                el.attrs = {}
                it = el.find(class_=re.compile(r'PlayerStats__Stat'))
                it.attrs = {}
                item['content_html'] += str(el)
            item['content_html'] += '</div>'
            content.decompose()

        content = page.find(class_=re.compile(r'Title-'))
        if content:
            el = page.find(class_=re.compile(r'ImpactLabel-'))
            if el:
                item['content_html'] += '<div style="padding-top:12px;"><span style="font-weight:bold; color:white; background-color:#444;">' + el.decode_contents() + '</span></div>'
                el.decompose()
                item['content_html'] += '<div style="font-size:1.2em; font-weight:bold;">'
            else:
                item['content_html'] += '<div style="font-size:1.2em; font-weight:bold; padding-top:12px;">'
            item['content_html'] += content.decode_contents() + '</div>'
            content.decompose()

        content = page.find(class_=re.compile(r'PlayInfo__MatchupContainer'))
        if content:
            item['content_html'] += '<div style="padding-top:8px;">'
            for el in content.find_all('span'):
                item['content_html'] += '<div style="font-weight:bold;">' + el.decode_contents() + '</div>'
            item['content_html'] += '</div>'
            content.decompose()

        it = page.find(class_=re.compile(r'Chin-'))
        if it:
            content = it.find_all(class_=re.compile(r'Typography__Component'))
            if content:
                for el in content:
                    if not el.find_parent(class_=re.compile(r'Footer-')):
                        item['content_html'] += str(el)

        content = page.find('amp-story-page-outlink')
        if content:
            item['content_html'] += utils.add_button(content.a['data-vars-button-link'], content.a['data-vars-button-text'])

        it = page.find(class_=re.compile(r'Footer'))
        if it:
            content = it.find_all(class_=re.compile(r'Typography__Component'))
            if content:
                for el in content:
                    item['content_html'] += '<div style="font-size:0.8em; text-align:right;">' + el.decode_contents() + '</div>'
            it.decompose()

        # content = page.find_all(class_=re.compile(r'Typography__Component'))
        # if content:
        #     for el in content:
        #         item['content_html'] += str(el)

        if has_text:
            item['content_html'] += '</td></tr>'

        item['content_html'] += '</table><div>&nbsp;</div>'
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


def get_content(url, args, site_json, save_debug=False):
    if '/stories/' in url:
        return get_story_content(url, args, site_json, save_debug)

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
        item['author']['name'] = 'MLB.com'

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
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(urlsplit(item['url']).netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
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
