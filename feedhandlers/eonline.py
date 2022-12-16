import html, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1024):
    split_url = urlsplit(img_src)
    return '{}://{}{}?fit=around%7C{}:1&output-quality=80'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def add_image(image, desc='', width=1024):
    captions = []
    if image.get('title'):
        captions.append(image['title'])
    if image.get('agency'):
        captions.append(image['agency'])
    return utils.add_image(resize_image(image['uri'], width), ' | '.join(captions), desc=desc)

def get_content_by_category(key):
    query = '''
    query CONTENT_BY_CATEGORY(
		$categoryKey: String!
		$edition: EDITIONKEY!
		$skip: Int
		$limit: Limit
	) {
		articles(
			filter: { categoryKey: $categoryKey, edition: $edition, skip: $skip, limit: $limit }
		) {
			nodes {
				type
				snipe
				shortTitle
				id
				title
				edition
				publishDate
				uri(edition: $edition)
				thumbnail(edition: $edition) {
					uri
					id
				}
			}
		}
	}
    '''
    variables = {"categoryKey": key, "edition": "US" }
    gql_json = utils.post_url('https://api-aggregate.eonline.com/graphql', json_data={"query": query, "variables": variables})
    if not gql_json:
        return None
    return gql_json['data']['articles']['nodes']


def get_content_linkables(key, content_types):
    query = '''
    query CONTENT_LINKABLES(
		$contentTypes: [CONTENT_TYPE]
		$categoryKey: String
		$edition: EDITIONKEY!
		$excludeBranded: Boolean
		$skip: Int
		$limit: Limit
	) {
		contentLinkables(
			filter: {
				contentTypes: $contentTypes
				categoryKey: $categoryKey
				edition: $edition
				excludeBranded: $excludeBranded
				skip: $skip
				limit: $limit
			}
		) {
			nodes {
				id
				title
				shortTitle
				uri(edition: $edition)
				snipe
				thumbnail(edition: $edition) {
					uri
					id
				}
				publishDate
				type
				... on Article {
					subhead
				}
				... on Gallery {
					subhead
				}
				... on Video {
					description
				}
			}
			totalCount
		}
	}
    '''
    variables = {"contentTypes": content_types, "categoryKey": key, "edition": "US" }
    gql_json = utils.post_url('https://api-aggregate.eonline.com/graphql', json_data={"query": query, "variables": variables})
    if not gql_json:
        return None
    return gql_json['data']['contentLinkables']['nodes']


def get_video(id):
    query = '''
    query VIDEO_DETAIL_BY_ID($id: ID!, $edition: EDITIONKEY!) {
		video(id: $id, edition: $edition) {
			id
			title
			uri(edition: $edition)
			videoUri
			duration
			publicId
			description
			publishDate
			expirationDate
			thumbnail(edition: $edition) {
				uri
				title
				sourceWidth
				sourceHeight
			}
			hdThumbnail {
				id
				uri
				title
				sourceWidth
				sourceHeight
			}
			pageMetaData(edition: $edition) {
				defaultUrl
				canonicalUrl
				redirectUrl
				hreflang {
					uri
					edition
				}
			}
			branding {
				brandingType
				displayText
				ads {
					adKeywords
				}
				adTracking {
					advertiser
				}
			}
			categories {
				id
				displayName(edition: $edition)
				title
				uri(edition: $edition)
				name
			}
			show(edition: $edition) {
				uri(edition: $edition)
				logo(edition: $edition) {
					id
					title
					uri
					sourceWidth
					sourceHeight
				}
				tuneIn
				youtubeAccountUrl
				facebookAccountUrl
				instagramAccountUrl
				twitterAccountUrl
				brandHexColor1
			}
		}
	}
    '''
    variables = {"id": id, "edition": "US" }
    gql_json = utils.post_url('https://api-aggregate.eonline.com/graphql', json_data={"query": query, "variables": variables})
    if not gql_json:
        return None
    return gql_json['data']['video']


def get_gallery(id):
    query = '''
    query GALLERY($id: ID!, $skip: Skip, $limit: Limit, $edition: EDITIONKEY!) {
		gallery(id: $id) {
			id
			title
			publishDate
			lastModDate
			subhead
			uri(edition: $edition)
			pageMetaData(edition: $edition) {
				canonicalUrl
				defaultUrl
				redirectUrl
				hreflang {
					edition
					uri
				}
			}
			thumbnail(edition: $edition) {
				uri
			}
			authors {
				fullName
			}
			categories(edition: $edition) {
				name
				displayName(edition: $edition)
			}
			branding {
				brandingType
				displayText
				ads {
					adKeywords
				}
				adTracking {
					advertiser
				}
			}
			show(edition: $edition) {
				id
				title
				uri(edition: $edition)
				logo(edition: $edition) {
					id
					sourceHeight
					sourceWidth
					title
					uri
				}
				tuneIn
				brandHexColor1
				instagramAccountUrl
				youtubeAccountUrl
				facebookAccountUrl
				twitterAccountUrl
			}
			additionalContentLink(edition: $edition) {
				title
				uri(edition: $edition)
				thumbnail(edition: $edition) {
					uri
					title
					sourceWidth
					sourceHeight
				}
			}
			galleryitems(filter: { skip: $skip, limit: $limit }) {
				nodes {
					image(edition: $edition) {
						uri
						id
						agency
						sourceWidth
						sourceHeight
						title
					}
					title
					caption
				}
				totalCount
			}
		}
	}
    '''
    variables = {"id": id, "edition": "US" }
    gql_json = utils.post_url('https://api-aggregate.eonline.com/graphql', json_data={"query": query, "variables": variables})
    if not gql_json:
        return None
    return gql_json['data']['gallery']


def get_article(id):
    query = '''
    query ARTICLE($id: ID!, $edition: EDITIONKEY!, $sanitizer: SANITIZATION_TYPE, $limit: Limit) {
		article(id: $id) {
			title
			shortTitle
			subhead
			autoPlayTopVideo
			pageMetaData(edition: $edition) {
				defaultUrl
				canonicalUrl
				redirectUrl
				ampRedirectUrl
				hreflang {
					uri
					edition
				}
			}
			uri(edition: $edition)
			edition
			publishDate
			lastModDate
			snipe
			enableVideoPlaylist
			thumbnail(edition: $edition) {
				uri
				title
			}
			translators
			authors {
				id
				fullName
				uri
			}
			categories(filterWorkflow: true) {
				id
				name
				displayName(edition: $edition)
				uri(edition: $edition)
				title
				key
			}
			branding {
				brandingType
				displayText
				ads {
					adKeywords
				}
				adTracking {
					advertiser
				}
			}
			show(edition: $edition) {
				uri(edition: $edition)
				logo(edition: $edition) {
					id
					title
					uri
					sourceWidth
					sourceHeight
				}
				tuneIn
				youtubeAccountUrl
				facebookAccountUrl
				instagramAccountUrl
				twitterAccountUrl
				brandHexColor1
			}
			segments(sanitizer: $sanitizer) {
				cta {
					id
					type
					uri(edition: $edition)
					title
					thumbnail(edition: $edition) {
						id
						title
						uri
						sourceWidth
						sourceHeight
					}
				}
				uri
				socialContent {
					id
					type
					oembedHtml
				}
				gallery {
					id
					title
					uri(edition: $edition)
					thumbnail(edition: $edition) {
						id
						title
						uri
					}
					galleryitems(filter: { limit: $limit }) {
						totalCount
						nodes {
							caption
							title
							image(edition: $edition) {
								id
								title
								uri
								sourceWidth
								sourceHeight
								agency
							}
						}
					}
				}
				text
				html
				type
				poll {
					id
					title
					isExpired
					isCaptchaEnabled
					isShowResult
					questions {
						questionId
						questionText
						choices {
							choiceId
							choiceText
							resultPercentage
							isWinner
						}
					}
					submitText
					submitMessage
					submitTitle
				}
				image(edition: $edition) {
					uri
					title
					id
					sourceWidth
					sourceHeight
					uri
					agency
				}
				video {
					id
					publicId
					title
					videoUri
					duration
					description
					publishDate
					expirationDate
					thumbnail {
						id
						title
						uri
					}
					hdThumbnail {
						id
						title
						uri
					}
				}
				productOffer {
					id
					image(edition: $edition) {
						id
						uri
					}
					itemTitle
					itemText
					productLinks {
						currentPrice
						originalPrice
						linkUri
						linkText
					}
				}
				checkoutItem {
					brandTitle
					buyButtonText
					channelKey
					id
					itemTitle
					image(edition: $edition) {
						title
						uri
						sourceHeight
						sourceWidth
					}
					itemText
					itemPrice
					productKey
					soldBy
				}
			}
		}
	}
	'''
    variables = {"id": id, "edition": "US" }
    gql_json = utils.post_url('https://api-aggregate.eonline.com/graphql', json_data={"query": query, "variables": variables})
    if not gql_json:
        return None
    return gql_json['data']['article']


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] == 'news':
        article_json = get_article(paths[1])
    elif paths[0] == 'photos':
        article_json = get_gallery(paths[1])
    elif paths[0] == 'videos':
        article_json = get_video(paths[1])

    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = paths[1]
    item['url'] = article_json['pageMetaData']['canonicalUrl']
    item['title'] = html.unescape(re.sub(r'</?i>', '', article_json['title'], flags=re.I))

    dt = datetime.fromisoformat(article_json['publishDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('lastModDate'):
        dt = datetime.fromisoformat(article_json['lastModDate'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('authors'):
        authors = []
        for it in article_json['authors']:
            authors.append(it['fullName'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = 'E! Online'

    if article_json.get('categories'):
        item['tags'] = []
        for it in article_json['categories']:
            item['tags'].append(it['name'])

    if article_json.get('thumbnail'):
        item['_image'] = article_json['thumbnail']['uri']

    item['content_html'] = ''
    if article_json.get('subhead'):
        item['summary'] = article_json['subhead']
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['subhead'])

    if article_json.get('videoUri'):
        video_src = utils.get_redirect_url(article_json['videoUri'])
        if '.mp4' in video_src:
            video_type = 'video/mp4'
        else:
            video_type = 'application/x-mpegURL'
        if article_json.get('hdThumbnail'):
            poster = article_json['hdThumbnail']['uri']
        else:
            poster = article_json['thumbnail']['uri']
        caption = 'Watch: ' + article_json['title']
        item['content_html'] += utils.add_video(video_src, video_type, poster, caption)
        if article_json.get('description'):
            item['content_html'] += '<p>{}</p>'.format(article_json['description'])

    if article_json.get('segments'):
        for segment in article_json['segments']:
            if segment['type'] == 'TEXT_ONLY':
                item['content_html'] += segment['text']

            elif segment['type'] == 'HTML_TEXT':
                soup = BeautifulSoup(segment['html'], 'html.parser')
                if soup.iframe:
                    item['content_html'] += utils.add_embed(soup.iframe['src'])
                else:
                    logger.warning('unhandled segment type HTML_TEXT in ' + item['url'])

            elif segment['type'] == 'PHOTO_ONLY':
                item['content_html'] += add_image(segment['image'])

            elif segment['type'] == 'PHOTO_TEXT':
                if segment.get('image'):
                    item['content_html'] += add_image(segment['image'])
                if segment.get('text'):
                    item['content_html'] += segment['text']

            elif segment['type'] == 'VIDEO_TEXT':
                if segment.get('video'):
                    video_src = utils.get_redirect_url(segment['video']['videoUri'])
                    if '.mp4' in video_src:
                        video_type = 'video/mp4'
                    else:
                        video_type = 'application/x-mpegURL'
                    if segment['video'].get('hdThumbnail'):
                        poster = segment['video']['hdThumbnail']['uri']
                    else:
                        poster = segment['video']['thumbnail']['uri']
                    if segment['video'].get('title'):
                        caption = 'Watch: ' + segment['video']['title']
                    else:
                        caption = ''
                    item['content_html'] += utils.add_video(video_src, video_type, poster, caption)
                if segment.get('text'):
                    item['content_html'] += segment['text']

            elif segment['type'] == 'VERTICAL_GALLERY':
                gallery_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, segment['gallery']['uri'])
                gallery_url = '{}/content?read&url={}'.format(config.server, quote_plus(gallery_url))
                item['content_html'] += '<table><tr><td><img src="{}" style="width:128px;" /></td><td><a href="{}"><span style="font-size:1.1em; font-weight:bold;">Gallery: {}</span></a></td></tr></table>'.format(resize_image(segment['gallery']['galleryitems']['nodes'][0]['image']['uri']), gallery_url, segment['gallery']['title'])

            elif segment['type'] == 'SOCIAL_CONTENT':
                if segment['socialContent']['type'] == 'twitter':
                    item['content_html'] += utils.add_embed(utils.get_twitter_url(segment['socialContent']['id']))
                elif segment['socialContent']['type'] == 'youtube':
                        item['content_html'] += utils.add_embed('https://www.youtube.com/embed/' + segment['socialContent']['id'])
                else:
                    logger.warning('unhandled social content type {} in {}'.format(segment['socialContent']['type'], item['url']))

            elif segment['type'] == 'ECOMMERCE':
                new_html = '<table><tr><td><img src="{}" style="width:128px;" /></td>'.format(resize_image(segment['productOffer']['image']['uri'], 128))
                new_html += '<td><span style="font-size:1.1em; font-weight:bold;">{}</span>{}<ul style="margin:0;">'.format(segment['productOffer']['itemTitle'], segment['productOffer']['itemText'])
                for it in segment['productOffer']['productLinks']:
                    text = it['currentPrice'] + ' '
                    if it.get('originalPrice'):
                        text += '<span style="font-size:0.8em; text-decoration:line-through;">{}</span> '.format(it['originalPrice'])
                    text += it['linkText']
                    new_html += '<li><a href="{}">{}</a></li>'.format(it['linkUri'], text)
                new_html += '</ul></td></tr></table>'
                soup = BeautifulSoup(new_html, 'html.parser')
                for el in soup.find_all('a'):
                    el['href'] = utils.get_redirect_url(el['href'])
                item['content_html'] += str(soup)

            elif segment['type'] == 'CALL_TO_ACTION' or segment['type'] == 'PROMO_TUNE_IN' or segment['type'] == 'SHOW_TUNE_IN':
                continue

            else:
                logger.warning('unhandled segment type {} in {}'.format(segment['type'], item['url']))

    if article_json.get('galleryitems'):
        for it in article_json['galleryitems']['nodes']:
            desc = ''
            if it.get('title'):
                desc += '<h4>{}</h4>'.format(it['title'])
            if it.get('caption'):
                desc += it['caption']
            item['content_html'] += add_image(it['image'], desc)

    item['content_html'] = re.sub(r'</(div|figure|table)>\s*<(div|figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(args, save_debug=False):
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 0:
        content_json = get_content_linkables('top_stories', ['ARTICLE', 'GALLERY', 'VIDEO'])
    elif len(paths) == 1:
        if paths[0] == 'news':
            content_json = get_content_linkables('top_stories', ['ARTICLE'])
        elif paths[0] == 'photos':
            content_json = get_content_linkables('top_stories', ['VIDEO'])
        elif paths[0] == 'photos':
            content_json = get_content_linkables('top_photos', ['GALLERY'])
    else:
        content_json = get_content_linkables(paths[1], ['ARTICLE', 'GALLERY', 'VIDEO'])
    if not content_json:
        return None
    if save_debug:
        utils.write_file(content_json, './debug/feed.json')

    n = 0
    items = []
    for article in content_json:
        url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['uri'])
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args and n == int(args['max']):
                    break

    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
