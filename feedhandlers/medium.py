import html, json, operator, re, requests
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from feedhandlers import rss, twitter
import utils

import logging
logger = logging.getLogger(__name__)

graphql_json = None

def medium_image_src(image_id, width=800):
  return 'https://miro.medium.com/max/{}/{}'.format(width, image_id)

def get_graphql(url, save_debug=False):
  split_url = urlsplit(url)

  s = requests.Session()
  headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
             "sec-ch-ua": "\"Google Chrome\";v=\"93\", \" Not;A Brand\";v=\"99\", \"Chromium\";v=\"93\""}
  r = s.get(url, headers=headers)
  if r.status_code == 200:
    body = {"operationName":"PostViewerEdgeContent","variables":{"postId":"","postMeteringOptions":{"referrer":""}},"query":"query PostViewerEdgeContent($postId: ID!, $postMeteringOptions: PostMeteringOptions) {\n  post(id: $postId) {\n    ... on Post {\n      id\n      viewerEdge {\n        id\n        fullContent(postMeteringOptions: $postMeteringOptions) {\n          isLockedPreviewOnly\n          validatedShareKey\n          bodyModel {\n            ...PostBody_bodyModel\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment PostBody_bodyModel on RichText {\n  sections {\n    name\n    startIndex\n    textLayout\n    imageLayout\n    backgroundImage {\n      id\n      originalHeight\n      originalWidth\n      __typename\n    }\n    videoLayout\n    backgroundVideo {\n      videoId\n      originalHeight\n      originalWidth\n      previewImageId\n      __typename\n    }\n    __typename\n  }\n  paragraphs {\n    id\n    ...PostBodySection_paragraph\n    __typename\n  }\n  ...normalizedBodyModel_richText\n  __typename\n}\n\nfragment normalizedBodyModel_richText on RichText {\n  paragraphs {\n    markups {\n      type\n      __typename\n    }\n    ...getParagraphHighlights_paragraph\n    ...getParagraphPrivateNotes_paragraph\n    __typename\n  }\n  sections {\n    startIndex\n    ...getSectionEndIndex_section\n    __typename\n  }\n  ...getParagraphStyles_richText\n  ...getParagraphSpaces_richText\n  __typename\n}\n\nfragment getParagraphHighlights_paragraph on Paragraph {\n  name\n  __typename\n  id\n}\n\nfragment getParagraphPrivateNotes_paragraph on Paragraph {\n  name\n  __typename\n  id\n}\n\nfragment getSectionEndIndex_section on Section {\n  startIndex\n  __typename\n}\n\nfragment getParagraphStyles_richText on RichText {\n  paragraphs {\n    text\n    type\n    __typename\n  }\n  sections {\n    ...getSectionEndIndex_section\n    __typename\n  }\n  __typename\n}\n\nfragment getParagraphSpaces_richText on RichText {\n  paragraphs {\n    layout\n    metadata {\n      originalHeight\n      originalWidth\n      __typename\n    }\n    type\n    ...paragraphExtendsImageGrid_paragraph\n    __typename\n  }\n  ...getSeriesParagraphTopSpacings_richText\n  ...getPostParagraphTopSpacings_richText\n  __typename\n}\n\nfragment paragraphExtendsImageGrid_paragraph on Paragraph {\n  layout\n  type\n  __typename\n  id\n}\n\nfragment getSeriesParagraphTopSpacings_richText on RichText {\n  paragraphs {\n    id\n    __typename\n  }\n  sections {\n    startIndex\n    __typename\n  }\n  __typename\n}\n\nfragment getPostParagraphTopSpacings_richText on RichText {\n  paragraphs {\n    layout\n    text\n    __typename\n  }\n  sections {\n    startIndex\n    __typename\n  }\n  __typename\n}\n\nfragment PostBodySection_paragraph on Paragraph {\n  name\n  ...PostBodyParagraph_paragraph\n  __typename\n  id\n}\n\nfragment PostBodyParagraph_paragraph on Paragraph {\n  name\n  type\n  ...ImageParagraph_paragraph\n  ...TextParagraph_paragraph\n  ...IframeParagraph_paragraph\n  ...MixtapeParagraph_paragraph\n  __typename\n  id\n}\n\nfragment IframeParagraph_paragraph on Paragraph {\n  iframe {\n    mediaResource {\n      id\n      iframeSrc\n      iframeHeight\n      iframeWidth\n      title\n      __typename\n    }\n    __typename\n  }\n  layout\n  ...getEmbedlyCardUrlParams_paragraph\n  ...Markups_paragraph\n  __typename\n  id\n}\n\nfragment getEmbedlyCardUrlParams_paragraph on Paragraph {\n  type\n  iframe {\n    mediaResource {\n      iframeSrc\n      __typename\n    }\n    __typename\n  }\n  __typename\n  id\n}\n\nfragment Markups_paragraph on Paragraph {\n  name\n  text\n  hasDropCap\n  dropCapImage {\n    ...MarkupNode_data_dropCapImage\n    __typename\n    id\n  }\n  markups {\n    type\n    start\n    end\n    href\n    anchorType\n    userId\n    linkMetadata {\n      httpStatus\n      __typename\n    }\n    __typename\n  }\n  __typename\n  id\n}\n\nfragment MarkupNode_data_dropCapImage on ImageMetadata {\n  ...DropCap_image\n  __typename\n  id\n}\n\nfragment DropCap_image on ImageMetadata {\n  id\n  originalHeight\n  originalWidth\n  __typename\n}\n\nfragment ImageParagraph_paragraph on Paragraph {\n  href\n  layout\n  metadata {\n    id\n    originalHeight\n    originalWidth\n    focusPercentX\n    focusPercentY\n    alt\n    __typename\n  }\n  ...Markups_paragraph\n  ...ParagraphRefsMapContext_paragraph\n  ...PostAnnotationsMarker_paragraph\n  __typename\n  id\n}\n\nfragment ParagraphRefsMapContext_paragraph on Paragraph {\n  id\n  name\n  text\n  __typename\n}\n\nfragment PostAnnotationsMarker_paragraph on Paragraph {\n  ...PostViewNoteCard_paragraph\n  __typename\n  id\n}\n\nfragment PostViewNoteCard_paragraph on Paragraph {\n  name\n  __typename\n  id\n}\n\nfragment TextParagraph_paragraph on Paragraph {\n  type\n  hasDropCap\n  ...Markups_paragraph\n  ...ParagraphRefsMapContext_paragraph\n  __typename\n  id\n}\n\nfragment MixtapeParagraph_paragraph on Paragraph {\n  text\n  type\n  mixtapeMetadata {\n    href\n    thumbnailImageId\n    __typename\n  }\n  markups {\n    start\n    end\n    type\n    href\n    __typename\n  }\n  __typename\n  id\n}\n"}
    body['variables']['postId'] = split_url.path.split('-')[-1]
    gql_url = '{}://{}/_/graphql'.format(split_url.scheme, split_url.netloc)
    r = s.post(gql_url, json=body)
    if r.status_code == 200:
      gql_json = r.json()
      utils.write_file(gql_json, './debug/medium.json')
      return gql_json
  return None

def get_content(url, args, save_debug=False):
  clean_url = utils.clean_url(url)
  split_url = urlsplit(clean_url)

  s = utils.requests_retry_session()
  headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
             "sec-ch-ua": "\"Google Chrome\";v=\"93\", \" Not;A Brand\";v=\"99\", \"Chromium\";v=\"93\""}
  r = s.get(url, headers=headers)
  if r.status_code != 200:
    return None

  article_html = r.text
  if save_debug:
    utils.write_file(article_html, './debug/debug.html')

  m = re.search(r'<script>window\.__APOLLO_STATE__ = ({.+?})<\/script>', article_html)
  if not m:
    logger.warning('No __APOLLO_STATE__ data found in ' + url)
    return None

  try:
    article_json = json.loads(m.group(1))
  except:
    logger.warning('Error loading __APOLLO_STATE__ json data from ' + url)
    if save_debug:
      utils.write_file(m.group(1), './debug/debug.txt')
    return None
  if save_debug:
    utils.write_file(article_json, './debug/debug.json')

  m = re.search(r'-([a-f0-9]+)$', clean_url)
  if m:
    post_id = m.group(1)
  else:
    for key in article_json['ROOT_QUERY']:
      if key.startswith('postResult'):
        m = re.search(r'\"id\":\"([a-f0-9]+)\"', key)
        if m:
          post_id = m.group(1)

  post = article_json['Post:' + post_id]

  item = {}
  item['id'] = post_id
  item['url'] = clean_url
  item['title'] = post['title']

  dt = datetime.fromtimestamp(post['firstPublishedAt']/1000).replace(tzinfo=timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromtimestamp(post['updatedAt']/1000).replace(tzinfo=timezone.utc)
  item['date_modified'] = dt.isoformat()

  if post.get('creator'):
    item['author'] = {}
    item['author']['name'] = article_json[post['creator']['__ref']]['name']

  tags = []
  if post.get('tags'):
    for tag in post['tags']:
      tags.append(article_json[tag['__ref']]['displayTitle'])
  if post.get('topics'):
    for tag in post['topics']:
      tags.append(tag['name'])
  if tags:
    item['tags'] = list(set(tags))

  if post.get('previewImage'):
    item['_image'] = medium_image_src(article_json[post['previewImage']['__ref']]['id'])

  if post.get('previewContent'):
    item['summary'] = post['previewContent']['subtitle']

  # Try to get the full content from graphql query
  gql_data = {"operationName":"PostViewerEdgeContent","variables":{"postId":"","postMeteringOptions":{"referrer":""}},"query":"query PostViewerEdgeContent($postId: ID!, $postMeteringOptions: PostMeteringOptions) {\n  post(id: $postId) {\n    ... on Post {\n      id\n      viewerEdge {\n        id\n        fullContent(postMeteringOptions: $postMeteringOptions) {\n          isLockedPreviewOnly\n          validatedShareKey\n          bodyModel {\n            ...PostBody_bodyModel\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment PostBody_bodyModel on RichText {\n  sections {\n    name\n    startIndex\n    textLayout\n    imageLayout\n    backgroundImage {\n      id\n      originalHeight\n      originalWidth\n      __typename\n    }\n    videoLayout\n    backgroundVideo {\n      videoId\n      originalHeight\n      originalWidth\n      previewImageId\n      __typename\n    }\n    __typename\n  }\n  paragraphs {\n    id\n    ...PostBodySection_paragraph\n    __typename\n  }\n  ...normalizedBodyModel_richText\n  __typename\n}\n\nfragment normalizedBodyModel_richText on RichText {\n  paragraphs {\n    markups {\n      type\n      __typename\n    }\n    ...getParagraphHighlights_paragraph\n    ...getParagraphPrivateNotes_paragraph\n    __typename\n  }\n  sections {\n    startIndex\n    ...getSectionEndIndex_section\n    __typename\n  }\n  ...getParagraphStyles_richText\n  ...getParagraphSpaces_richText\n  __typename\n}\n\nfragment getParagraphHighlights_paragraph on Paragraph {\n  name\n  __typename\n  id\n}\n\nfragment getParagraphPrivateNotes_paragraph on Paragraph {\n  name\n  __typename\n  id\n}\n\nfragment getSectionEndIndex_section on Section {\n  startIndex\n  __typename\n}\n\nfragment getParagraphStyles_richText on RichText {\n  paragraphs {\n    text\n    type\n    __typename\n  }\n  sections {\n    ...getSectionEndIndex_section\n    __typename\n  }\n  __typename\n}\n\nfragment getParagraphSpaces_richText on RichText {\n  paragraphs {\n    layout\n    metadata {\n      originalHeight\n      originalWidth\n      __typename\n    }\n    type\n    ...paragraphExtendsImageGrid_paragraph\n    __typename\n  }\n  ...getSeriesParagraphTopSpacings_richText\n  ...getPostParagraphTopSpacings_richText\n  __typename\n}\n\nfragment paragraphExtendsImageGrid_paragraph on Paragraph {\n  layout\n  type\n  __typename\n  id\n}\n\nfragment getSeriesParagraphTopSpacings_richText on RichText {\n  paragraphs {\n    id\n    __typename\n  }\n  sections {\n    startIndex\n    __typename\n  }\n  __typename\n}\n\nfragment getPostParagraphTopSpacings_richText on RichText {\n  paragraphs {\n    layout\n    text\n    __typename\n  }\n  sections {\n    startIndex\n    __typename\n  }\n  __typename\n}\n\nfragment PostBodySection_paragraph on Paragraph {\n  name\n  ...PostBodyParagraph_paragraph\n  __typename\n  id\n}\n\nfragment PostBodyParagraph_paragraph on Paragraph {\n  name\n  type\n  ...ImageParagraph_paragraph\n  ...TextParagraph_paragraph\n  ...IframeParagraph_paragraph\n  ...MixtapeParagraph_paragraph\n  __typename\n  id\n}\n\nfragment IframeParagraph_paragraph on Paragraph {\n  iframe {\n    mediaResource {\n      id\n      iframeSrc\n      iframeHeight\n      iframeWidth\n      title\n      __typename\n    }\n    __typename\n  }\n  layout\n  ...getEmbedlyCardUrlParams_paragraph\n  ...Markups_paragraph\n  __typename\n  id\n}\n\nfragment getEmbedlyCardUrlParams_paragraph on Paragraph {\n  type\n  iframe {\n    mediaResource {\n      iframeSrc\n      __typename\n    }\n    __typename\n  }\n  __typename\n  id\n}\n\nfragment Markups_paragraph on Paragraph {\n  name\n  text\n  hasDropCap\n  dropCapImage {\n    ...MarkupNode_data_dropCapImage\n    __typename\n    id\n  }\n  markups {\n    type\n    start\n    end\n    href\n    anchorType\n    userId\n    linkMetadata {\n      httpStatus\n      __typename\n    }\n    __typename\n  }\n  __typename\n  id\n}\n\nfragment MarkupNode_data_dropCapImage on ImageMetadata {\n  ...DropCap_image\n  __typename\n  id\n}\n\nfragment DropCap_image on ImageMetadata {\n  id\n  originalHeight\n  originalWidth\n  __typename\n}\n\nfragment ImageParagraph_paragraph on Paragraph {\n  href\n  layout\n  metadata {\n    id\n    originalHeight\n    originalWidth\n    focusPercentX\n    focusPercentY\n    alt\n    __typename\n  }\n  ...Markups_paragraph\n  ...ParagraphRefsMapContext_paragraph\n  ...PostAnnotationsMarker_paragraph\n  __typename\n  id\n}\n\nfragment ParagraphRefsMapContext_paragraph on Paragraph {\n  id\n  name\n  text\n  __typename\n}\n\nfragment PostAnnotationsMarker_paragraph on Paragraph {\n  ...PostViewNoteCard_paragraph\n  __typename\n  id\n}\n\nfragment PostViewNoteCard_paragraph on Paragraph {\n  name\n  __typename\n  id\n}\n\nfragment TextParagraph_paragraph on Paragraph {\n  type\n  hasDropCap\n  ...Markups_paragraph\n  ...ParagraphRefsMapContext_paragraph\n  __typename\n  id\n}\n\nfragment MixtapeParagraph_paragraph on Paragraph {\n  text\n  type\n  mixtapeMetadata {\n    href\n    thumbnailImageId\n    __typename\n  }\n  markups {\n    start\n    end\n    type\n    href\n    __typename\n  }\n  __typename\n  id\n}\n"}
  gql_data['variables']['postId'] = post_id
  gql_url = 'https://{}/_/graphql'.format(split_url.netloc)
  r = s.post(gql_url, json=gql_data)
  if r.status_code == 200:
    gql_json = r.json()
    paragraphs = gql_json['data']['post']['viewerEdge']['fullContent']['bodyModel']['paragraphs']
    if save_debug:
      utils.write_file(gql_json, './debug/medium.json')
  else:
    # If that failed, use what content was embedded
    for key in post.keys():
      if key.startswith('content({\"postMeteringOptions'):
        paragraphs = post[key]['bodyModel']['paragraphs']
        break

  is_list = ''
  content_html = ''
  for p in paragraphs:
    if p.get('__ref'):
      paragraph = article_json[p['__ref']]
    else:
      paragraph = p

    paragraph_type = paragraph['type'].lower()

    # Skip the first paragraph if since it's usually the title
    if paragraph['id'].endswith('_0') and paragraph_type == 'h3':
      continue

    if is_list and not (paragraph_type == 'oli' or paragraph_type == 'uli'):
      start_tag = '</{}>'.format(is_list)
      is_list = ''
    else:
      start_tag = ''
  
    if paragraph_type == 'p' or paragraph_type == 'h1' or paragraph_type == 'h2' or paragraph_type == 'h3' or paragraph_type == 'h4':
      start_tag += '<{}>'.format(paragraph_type)
      end_tag = '</{}>'.format(paragraph_type)
      paragraph_text = paragraph['text']

    elif paragraph_type == 'img':
      if paragraph['metadata'].get('__ref'):
        image = article_json[paragraph['metadata']['__ref']]
      else:
        image = paragraph['metadata']
      start_tag += '<div class="image"><figure><img width="100%" src="{}" /><figcaption><small>'.format(medium_image_src(image['id']))
      end_tag = '</small></figcaption></figure></div>'
      paragraph_text = paragraph['text']

    elif paragraph_type == 'pre':
      start_tag += '<pre style="margin-left:2em; padding:0.5em; white-space:pre-wrap; background:#F2F2F2;">'
      end_tag = '</pre>'
      if not paragraph.get('markups'):
        # Escape HTML characters so they are not rendered
        paragraph_text = html.escape(paragraph['text'])
      else:
        # If there are markups, escaping the characters will mess up the alignment
        paragraph_text = paragraph['text']

    elif paragraph_type == 'bq' or paragraph_type == 'pq':
      start_tag += '<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;">'
      end_tag = '</blockquote>'
      paragraph_text = paragraph['text']

    elif paragraph_type == 'oli' or paragraph_type == 'uli':
      if is_list:
        start_tag += '<li>'
        end_tag = '</li>'
      else:
        if paragraph_type == 'oli':
          is_list = 'ol'
        else:
          is_list = 'ul'
        start_tag += '<{}><li>'.format(is_list)
        end_tag = '</li>'
      paragraph_text = paragraph['text']

    elif paragraph_type == 'iframe':
      if paragraph['iframe']['mediaResource'].get('__ref'):
        media_resource = article_json[paragraph['iframe']['mediaResource']['__ref']]
      else:
        media_resource = paragraph['iframe']['mediaResource']

      iframe_src = media_resource['iframeSrc']
      if iframe_src.startswith('https://cdn.embedly.com'):
        # This is usually embeded media
        iframe_query = parse_qs(urlsplit(iframe_src).query)
        if 'src' in iframe_query:
          iframe_src = iframe_query['src'][0]
        elif 'url' in iframe_query:
          iframe_src = iframe_query['url'][0]
        start_tag += utils.add_embed(iframe_src, save_debug)
        end_tag = ''
        paragraph_text = ''
      elif not iframe_src:
        # This is usually code from a github gist
        r = s.get('{}://{}/media/{}'.format(split_url.scheme, split_url.netloc,  media_resource['id']))
        if r.status_code == 200:
          iframe_html = r.text
          if save_debug:
            utils.write_file(iframe_html, './debug/iframe.html')
          m = re.search(r'src="https:\/\/gist\.github\.com\/([^\/]+)\/([^\.]+)\.js"', iframe_html)
          if m:
            r = s.get('https://gist.githubusercontent.com/{}/{}/raw'.format(m.group(1), m.group(2)))
            if r.status_code == 200:
              iframe_html = r.text
              start_tag += '<pre style="margin-left:2em; padding:0.5em; white-space:pre-wrap; background:#F2F2F2;">{}</pre>'.format(iframe_html)
              end_tag = ''
              paragraph_text = ''
        if r.status_code != 200 or not m:
          logger.warning('unhandled Medium media iframe in ' + url)
      else:
        logger.warning('unhandled Medium iframe content in ' + url)
        start_tag += '<p>Embedded content from <a href="{0}">{0}</a></p>'.format(iframe_src)
        end_tag = ''
        paragraph_text = ''

    elif paragraph_type == 'mixtape_embed':
      mixtape = paragraph['mixtapeMetadata']
      #start_tag += '<table style="width:80%; height:5em; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px;"><tr><td><a style="text-decoration:none;" href="{}"><small>'.format(mixtape['href'])
      #end_tag = '</small></a></td><td style="padding:0;"><img style="height:5em; display:block; border-top-right-radius:10px; border-bottom-right-radius:10px;" src="{}" /></td></tr></table>'.format(medium_image_src(mixtape['thumbnailImageId'], 200))
      start_tag += '<blockquote><ul><li>'
      end_tag = '</li></ul></blockquote>'
      paragraph_text = paragraph['text']

    else:
      logger.warning('unhandled paragraph type {} in {}'.format(paragraph_type, url))
      continue

    if paragraph.get('markups'):
      starts = list(map(operator.itemgetter('start'), paragraph['markups']))
      ends = list(map(operator.itemgetter('end'), paragraph['markups']))
      markup_text = paragraph_text[0:min(starts)]
      for i in range(min(starts), max(ends)+1):
        for n in range(len(starts)):
          if starts[n] == i:
            markup_type = paragraph['markups'][n]['type'].lower()
            if markup_type == 'a':
              markup_text += '<a href="{}">'.format(paragraph['markups'][n]['href'])
            elif markup_type == 'code' or markup_type == 'em' or markup_type == 'strong':
              markup_text += '<{}>'.format(markup_type)
            else:
              logger.warning('unhandled markup type {} in {}'.format(markup_type, url))
            starts[n] = -1

        for n in reversed(range(len(ends))):
          if ends[n] == i:
            markup_type = paragraph['markups'][n]['type'].lower()
            if markup_type == 'a' or markup_type == 'code' or markup_type == 'em' or markup_type == 'strong':
              markup_text += '</{}>'.format(markup_type)
            else:
              logger.warning('unhandled markup type {} in {}'.format(markup_type, url))
            ends[n] = -1

        if i < len(paragraph_text):
          markup_text += paragraph_text[i]

      markup_text += paragraph_text[i+1:]
    else:
      markup_text = paragraph_text
    markup_text = markup_text.replace('\n', '<br />')

    content_html += start_tag + markup_text + end_tag

  # Close an open list tag if it was the last element
  if is_list:
    content_html += '</{}>'.format(is_list)

  # Remove the title
  #content_html = re.sub(r'<h3.*>{}<.*\/h3>'.format(item['title']), '', content_html)

  item['content_html'] = content_html
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)