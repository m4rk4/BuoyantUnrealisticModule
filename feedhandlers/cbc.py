import pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_video(media_id):
    bistro_json = utils.get_url_json('https://www.cbc.ca/bistro/order?mediaId={}'.format(media_id))
    if bistro_json and not bistro_json.get('errors'):
        media_json = bistro_json['items'][0]
        caption = '<a href="{}">{}</a>'.format(media_json['pageUrl'], media_json['title'])
        video = next((it for it in media_json['assetDescriptors'] if (it.get('mimeType') and it['mimeType'] == 'video/mp4')), None)
        if video:
            return utils.add_video(video['key'], 'video/mp4', media_json['thumbnail'],caption)
        else:
            caption = '<b>Video unavailable:<b> ' + caption
            return utils.add_image(media_json['thumbnail'], caption)

    caption = '<b>Video unavailable:<b> '
    if bistro_json and bistro_json.get('errors'):
        caption += bistro_json['errors'][0]['message']
    return utils.add_image('{}/image?width=640&height=360'.format(config.server), caption)


def add_image(image_block, width=1180):
    captions = []
    if image_block.get('description'):
        captions.append(image_block['description'])
    if image_block.get('credit'):
        captions.append(image_block['credit'])

    if image_block.get('originalimageurl'):
        img_src = image_block['originalimageurl']
    elif image_block.get('url'):
        img_src = image_block['url']

    image_json = None
    image = None
    images = []
    if image_block.get('jsonurl'):
        image_json = utils.get_url_json('https://www.cbc.ca' + image_block['jsonurl'])
    else:
        split_url = urlsplit(img_src)
        paths = list(filter(None, split_url.path.split('/')))
        if image_block.get('sourceId'):
            img_id = image_block['sourceId']
        else:
            img_id = image_block['id']
        image_json = utils.get_url_json('https://www.cbc.ca/json/cmlink/{}-{}'.format(paths[-1].split('.')[0], img_id))
    if image_json:
        for key, val in image_json['derivatives'].items():
            if key.startswith('original_'):
                images.append(val)
        if images:
            image = utils.closest_dict(images, 'w', width)
    if image:
        for key, val in image_block['derivatives'].items():
            images.append(val)
        if images:
            image = utils.closest_dict(images, 'w', width)
    if image:
        return utils.add_image(image['fileurl'], ' | '.join(captions))
    else:
        return utils.add_image(image_block['originalimageurl'], ' | '.join(captions))


def format_block(block):
    block_html = ''
    end_tag = ''
    #print(block)
    if block['type'] == 'text':
        block_html += block['content']

    elif block['type'] == 'html':
        if block['tag'] == 'a':
            block_html += '<a href="{}">'.format(block['attribs']['href'])
            end_tag = '</a>'
        elif block['tag'] == 'br':
            block_html += '<br/>'
        elif block['tag'] == 'hr':
            block_html += '<hr/>'
        elif block['tag'] == 'blockquote' and block.get('attribs') and block['attribs'].get('class') and 'pullquote' in block['attribs']['class']:
            quote = next((it for it in block['content'] if it['type'] == 'text'), None)
            cite = next((it for it in block['content'] if (it['type'] == 'html' and it['tag'] == 'cite')), None)
            if cite:
                author = re.sub('^- ', '', cite['content'][0]['content'])
            else:
                author = ''
            block_html += utils.add_pullquote(quote['content'], author)
            return block_html
        elif (block['tag'] == 'span' or block['tag'] == 'p') and (block.get('content') and isinstance(block['content'], list) and len(block['content']) == 1 and re.search(r'polopoly_', block['content'][0]['type'])):
            pass
        elif block['tag'] == 'span' and not block.get('attribs') and block.get('content') and isinstance(block['content'], list) and len(block['content']) == 1 and block['content'][0]['type'] == 'text':
            pass
        elif re.search(r'\b(em|h\d|li|ol|p|strong|u|ul)\b', block['tag']):
            block_html += '<{}>'.format(block['tag'])
            end_tag = '</{}>'.format(block['tag'])
        else:
            logger.warning('unhandled html tag ' + block['tag'])

    elif block['type'] == 'polopoly_image':
        block_html += add_image(block['content'])

    elif block['type'] == 'polopoly_media':
        block_html += add_video(block['content']['mediaId'])

    elif block['type'] == 'polopoly_embed':
        if block['content']['type'] == 'youtube':
            block_html += utils.add_embed('https://www.youtube.com/embed/' + block['content']['id'])
        elif block['content']['type'] == 'twitter':
            block_html += utils.add_embed(block['content']['url'])
        elif block['content']['type'] == 'facebookpost' or block['content']['type'] == 'facebookvideo':
            block_html += utils.add_embed(block['content']['url'])
        elif block['content']['type'] == 'datawrapper':
            block_html += utils.add_embed(block['content']['url'])
        elif block['content']['type'] == 'customhtml':
            soup = BeautifulSoup(block['content']['html'], 'html.parser')
            if soup.iframe:
                block_html += utils.add_embed(soup.iframe['src'])
            elif soup.blockquote and soup.blockquote.get('cite'):
                block_html += utils.add_embed(soup.blockquote['cite'])
            else:
                logger.warning('unknown polopoly_embed customhtml')
        elif block['content']['type'] == 'customhtml' and re.search(r'iframe', block['content']['html']):
            m = re.search(r'src="([^"]+)"', block['content']['html'])
            if m:
                block_html += utils.add_embed(m.group(1))
        else:
            logger.warning('unhandled polopoly_embed type ' + block['content']['type'])

    elif block['type'] == 'facebookpost' or block['type'] == 'facebookvideo':
        block_html += utils.add_embed(block['object']['url'])

    elif block['type'] == 'datawrapper':
        block_html += utils.add_embed(block['object']['url'])

    elif block['type'] == 'polopoly_similar':
        pass

    else:
        logger.warning('unhandled block type ' + block['type'])

    if block.get('content') and isinstance(block['content'], list):
        for blk in block['content']:
            block_html += format_block(blk)

    if end_tag:
        block_html += end_tag

    return block_html


def get_player_content(url, args, site_json, save_debug):
    m = re.search(r'https://www\.cbc\.ca/player/play/(\d+)$', url)
    if not m:
        logger.warning('unable to determine mediaId from ' + url)
        return None
    bistro_json = utils.get_url_json('https://www.cbc.ca/bistro/order?mediaId={}'.format(m.group(1)))
    if not bistro_json:
        return None
    if save_debug:
        utils.write_file(bistro_json, './debug/debug.json')

    if bistro_json.get('errors'):
        logger.warning('Video unavailable: ' + bistro_json['errors'][0]['message'])
        return None

    media_json = bistro_json['items'][0]

    item = {}
    item['id'] = media_json['id']
    item['url'] = media_json['pageUrl']
    item['title'] = media_json['title']

    tz_loc = pytz.timezone('US/Eastern')
    dt_loc = datetime.fromtimestamp(int(media_json['airDate']) / 1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_loc = datetime.fromtimestamp(int(media_json['addedDate']) / 1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    if media_json.get('showName'):
        item['author'] = {
            "name": media_json['showName']
        }
    else:
        item['author'] = {
            "name": "CBC.ca Video"
        }
    item['authors'] = []
    item['authors'].append(item['author'])

    if media_json.get('keywords'):
        item['tags'] = media_json['keywords'].split(', ')

    if media_json.get('thumbnail'):
        item['image'] = media_json['thumbnail']
        poster = item['image']
    else:
        poster = ''

    item['content_html'] = ''
    caption = '<a href="{}">{}</a>'.format(item['url'], item['title'])
    video = next((it for it in media_json['assetDescriptors'] if (it.get('mimeType') and it['mimeType'] == 'video/mp4')), None)
    if video:
        item['_video'] = video['key']
        item['content_html'] += utils.add_video(item['_video'], 'video/mp4', poster, '<b>Watch:</b> ' + caption)
    else:
        item['content_html'] += utils.add_image(poster, '<b>Video unavailable:</b> ' + caption)

    if media_json.get('description'):
        item['summary'] = media_json['description']
        if 'embed' not in args:
            item['content_html'] += '<p>{}</p>'.format(item['summary'])

    return item


def get_content(url, args, site_json, save_debug=False):
    if url.startswith('https://www.cbc.ca/player/play/'):
        return get_player_content(url, args, site_json, save_debug)
    elif url.startswith('https://www.cbc.ca/listencards/listencard/'):
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            el =  soup.find('a', class_='listen-card-link')
            if el:
                return utils.get_content(el['href'], args, False)
            else:
                logger.warning('unhandled listen card in ' + url)
        return None

    split_url = urlsplit(url)
    m = re.search(r'([0-9\.]+)$', split_url.path)
    if not m:
        logger.warning('unable to determine sourceId from ' + url)
        return None
    post_data = {
        "query":"\n    query {{\n        contentItem(sourceId: \"{}\", contentStatus:\"\") {{\n            deck\n            byline\n            type\n            wordcount: wordCount\n            id\n            corrections {{\n              correction\n              date\n            }}\n            clarifications {{\n              clarification\n              date\n            }}\n            mediaid: mediaId\n            flag\n            publishedAt\n            updatedAt\n            url\n            externalLinks {{\n              type\n              title\n              url\n            }}\n            shareHeadline\n            highlights {{\n              highlight\n              label\n            }}\n            intlinks {{\n              url\n              flag\n              shareHeadline\n              title\n              type\n            }}\n            authorDisplay\n            authors {{\n              name\n              smallImageUrl\n              title\n              biography\n              url\n              photoDerivatives {{\n                square_140 {{\n                  ...derivative\n                }}\n                square_300 {{\n                  ...derivative\n                }}\n                square_620 {{\n                  ...derivative\n                }}\n              }}\n              links {{\n                title\n                type\n                url\n              }}\n            }}\n            departments {{\n              name\n              label\n            }}\n            body {{\n              containsAudio\n              containsVideo\n              containsPhotogallery\n              parsed\n            }}\n            tracking {{\n              contentarea\n              contenttype\n              subsection1\n              subsection2\n              subsection3\n              subsection4\n            }}\n            advertising {{\n              site\n              zone\n              contentcategory\n              categorization\n              section\n              exclusions\n              category\n            }}\n            sponsor {{\n              external\n              name\n              image {{\n                derivative(preferredWidth:620) {{\n                  fileurl\n                }}\n              }}\n              label\n              link: url\n            }}\n            imageLarge\n            leadmedia {{\n              ...leadMedia\n            }}\n            headlineimage {{\n              ...leadMedia\n            }}\n            media: poloMedia {{\n              ...media\n            }}\n            segmentmedia {{\n              ...media\n            }}\n            episodemedia {{\n              ...media\n            }}\n            headlineData {{\n              type\n              publishedAt\n              mediaDuration\n              mediaId\n            }}\n            socialNetworks {{\n              facebook\n            }}\n            jsonLD\n            commentsEnabled\n            section {{\n              social {{\n                commentsSection\n              }}\n            }}\n            tags {{\n              name\n              type\n            }}\n            concepts {{\n              type\n              path\n            }}\n            newsletter\n            language\n            categories {{\n              attributionLevels {{\n                level1\n                level2\n                level3\n              }}\n            }}\n            attribution {{\n              level1\n              level2\n              level3\n            }}\n            title\n            description\n            editorialSource\n            poloEpisode {{\n              id\n              flag\n              url\n              title\n              headline\n              segments {{\n                ...segment\n              }}\n            }}\n            segments {{\n              ...segment\n            }}\n            photoGallery {{\n                aspectRatio\n                images {{\n                sourceId\n                localDescription\n                image {{\n                  credit\n                  derivatives\n                  altText\n                }}\n              }}\n            }}\n          }}\n        }}\n        \nfragment leadMedia on LeadMedia {{\n    id\n    deck\n    description\n    title\n    type\n    url\n    altText\n    showcaption\n    derivatives {{\n      ...derivatives\n    }}\n    credit\n    headline\n    size\n    useoriginalimage\n    originalimageurl\n    guid\n    runtime\n  }}\n        \nfragment derivatives on ImageDerivatives {{\n    _16x9_940 {{\n      ...derivative\n    }}\n    _16x9_300 {{\n      ...derivative\n    }}\n    _16x9_620 {{\n      ...derivative\n    }}\n    original_620 {{\n      ...derivative\n    }}\n    original_300 {{\n      ...derivative\n    }}\n    _16x9tight_140 {{\n      ...derivative\n    }}\n    _16x9_460 {{\n      ...derivative\n    }}\n  }}\n\n        \nfragment derivative on ImageDerivative {{\n    w\n    h\n    fileurl\n  }}\n\n        \nfragment media on Media {{\n    description\n    epoch {{\n      pubdate\n    }}\n    extattrib {{\n      captionUrl\n      guid\n      liveondemand\n      mediatype\n      runtime\n    }}\n    headlineimage {{\n      url\n    }}\n    show\n    showcaption\n    title\n}}\n\n        \nfragment segment on PolopolySegment {{\n  id\n\tflag\n\turl\n\ttitle\n\theadline\n}}\n\n    ".format(m.group(1))
    }
    graphql_json = utils.post_url('https://www.cbc.ca/graphql', json_data=post_data, use_proxy=True, use_curl_cffi=True)
    if not graphql_json:
        return None
    if save_debug:
        utils.write_file(graphql_json, './debug/debug.json')

    content_json = graphql_json['data']['contentItem']
    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['url']
    item['title'] = content_json['title']

    tz_loc = pytz.timezone('US/Eastern')
    dt_loc = datetime.fromtimestamp(int(content_json['publishedAt']) / 1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_loc = datetime.fromtimestamp(int(content_json['updatedAt']) / 1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    if content_json.get('authors'):
        item['authors'] = []
        for it in content_json['authors']:
            item['authors'].append({"name": it['name']})
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    elif content_json.get('byline'):
        item['author'] = {
            "name": content_json['byline']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    item['tags'] = []
    for it in content_json['tags']:
        item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    if content_json.get('headlineimage'):
        item['image'] = content_json['headlineimage']['originalimageurl']
    elif content_json.get('storyimages'):
        item['image'] = content_json['storyimages'][0]['originalimageurl']

    item['summary'] = content_json['description']

    item['content_html'] = ''
    if content_json.get('deck'):
        item['content_html'] += '<p><em>{}</em></p>'.format(content_json['deck'])

    if content_json['type'] == 'video':
        item['content_html'] += add_video(content_json['mediaid'])
    else:
        if content_json.get('headlineimage'):
            item['content_html'] += add_image(content_json['headlineimage'])

        for block in content_json['body']['parsed']:
            item['content_html'] += format_block(block)
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.cbc.ca/rss/
    return rss.get_feed(url, args, site_json, save_debug, get_content)
