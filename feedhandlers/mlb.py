import re
from bs4 import BeautifulSoup
from datetime import datetime
from markdown2 import markdown
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


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

    item['content_html'] = ''
    if article_json.get('subHeadline'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['subHeadline'])

    for part in article_json['parts']:
        if part['__typename'] == 'Markdown':
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
            item['content_html'] += utils.add_video(part['mp4AvcPlayback'], 'video/mp4', img_src, caption)

        elif part['__typename'] == 'OEmbed':
            if part['providerName'] == 'Twitter':
                soup = BeautifulSoup(part['html'], 'html.parser')
                links = soup.find_all('a')
                item['content_html'] += utils.add_embed(links[-1]['href'])
            else:
                logger.warning('unhandled oembed provider {} in {}'.format(part['providerName'], item['url']))

        else:
            logger.warning('unhandled content part type {} in {}'.format(part['__typename'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
