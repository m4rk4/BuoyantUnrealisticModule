import re
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'topic' in paths:
        logger.warning('unhandled url ' + url)
        return None
    gql_query = {
        "operationName": "GetContent",
        "variables": {
            "year": int(paths[-4]),
            "month": int(paths[-3]),
            "day": int(paths[-2]),
            "slug": paths[-1]
        },
        "query": "\n  query GetContent($year: Int!, $month: Int!, $day: Int!, $slug: String!, $previewToken: String) {\n    content(year: $year, month: $month, day: $day, slug: $slug, previewToken: $previewToken) {\n      ...contentFragment\n      ...articleFragment\n      ...imageFragment\n      ...videoFragment\n      ...pdfFragment\n      ...galleryFragment\n      ...flashGraphicFragment\n      ...widgetFragment\n    }\n  }\n  \n  fragment contentFragment on ContentGQL {\n    __typename\n    title\n    subtitle\n    description\n    contributorOverride\n    createdOn\n    modifiedOn\n    showAds\n    searchable\n    slug\n    url\n\n    group {\n      name\n      # TODO: add the rest of the ContentGroup fields as needed\n    }\n\n    contributors {\n      name\n      url\n    }\n\n    multimediaContributors {\n      name\n      url\n    }\n\n    tags {\n      text\n      url\n    }\n\n    issue {\n      issueDate\n    }\n\n    section {\n      name\n    }\n\n    subsection {\n      text\n      url\n    }\n\n    fmSubsection\n\n    flybySubsection\n\n    relContent {\n      title\n      url\n      contributors {\n        name\n        url\n      }\n\n      # NOTE: imgUrl should be queried for on a case by case\n      # basis to prevent the download of unnecessarily large images\n      # imgUrl(width: xxx, height: xxx)\n    }\n\n    mainContent {\n      __typename\n      description\n      contributors {\n        name\n        url\n      }\n      ... on ImageGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on FlashGraphicGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on GalleryGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on VideoGQL {\n        videoId\n      }\n    }\n\n    # NOTE: imgUrl should be queried for on a case by case\n    # basis to prevent the download of unnecessarily large images\n    # imgUrl(width: xxx, height: xxx)\n\n    # other generic content fields that we probably won't use:\n    # slug\n    # priority\n    # searchable\n    # paginate\n    # numComments\n    # frontpage\n  }\n\n  fragment articleFragment on ContentGQL {\n    ... on ArticleGQL {\n      layout\n      paragraphs\n      authorDescript\n      bylineType\n      mainTag\n      hasJump\n      textBeforeJump\n\n      shortcodes {\n        __typename\n        key\n        ...shortcodeFragment\n      }\n\n      recArticles {\n        title\n        url\n        description\n      }\n\n      prevArticle {\n        title\n        url\n        description\n      }\n      tags {\n        text\n        url\n      }\n      mainTag\n      description\n      shortcodes {\n        __typename\n        key\n        ...shortcodeFragment\n      }\n    }\n  }\n  \n  fragment imageFragment on ContentGQL {\n    ... on ImageGQL {\n      imgUrl(width: 1500, height: 1000)\n    }\n  }\n\n  fragment videoFragment on ContentGQL {\n    ... on VideoGQL {\n      videoId\n    }\n  }\n\n  fragment pdfFragment on ContentGQL {\n    ... on PdfGQL {\n      documentUrl\n    }\n  }\n\n  fragment galleryFragment on ContentGQL {\n    ... on GalleryGQL {\n      images {\n        imgUrl(width: 1500, height: 1500)\n        description\n        title\n        contributors {\n          name\n          url\n        }\n      }\n    }\n  }\n\n  fragment flashGraphicFragment on ContentGQL {\n    ... on FlashGraphicGQL {\n      graphicUrl\n      width\n      height\n    }\n  }\n\n  fragment widgetFragment on ContentGQL {\n    ... on WidgetGQL {\n      html\n      javascript\n      isHighcharts\n      isD3\n    }\n  }\n\n  fragment shortcodeFragment on ShortcodeInterface {\n    ...shortcodeImageFragment\n    ...shortcodeVimeoFragment\n    ...shortcodePullquoteFragment\n    ...shortcodeYoutubeFragment\n    ...shortcodeSpotifyFragment\n    ...shortcodeSoundFragment\n    ...shortcodeBoxQuoteFragment\n    ...shortcodeDropcapFragment\n    ...shortcodeDocumentCloudFragment\n    ...shortcodeExtContFragment\n    ...shortcodeFlashGraphicFragment\n    ...shortcodeGalleryFragment\n    ...shortcodePdfFragment\n    ...shortcodeWidgetFragment\n    ...shortcodeTextEffectFragment\n    ...shortcodeImageFadeInFragment\n    ...shortcodeGoogleFormFragment\n    ...shortcodePreviewFragment\n    ...shortcodeSponsorFragment\n    ...shortcodeTweetFragment\n  }\n\n  fragment shortcodeImageFragment on ShortcodeInterface {\n    ... on ShortcodeImageGQL {\n      byline\n      imageUrl\n      caption\n      contributors {\n        name\n        url\n      }\n      pos\n      size\n    }\n  }\n\n  fragment shortcodeVimeoFragment on ShortcodeInterface {\n    ... on ShortcodeVimeoGQL {\n      videoId\n      caption\n    }\n  }\n\n  fragment shortcodePullquoteFragment on ShortcodeInterface {\n    ... on ShortcodePullquoteGQL {\n      text\n      font\n      pos\n      size\n    }\n  }\n\n  fragment shortcodeYoutubeFragment on ShortcodeInterface {\n    ... on ShortcodeYoutubeGQL {\n      videoId\n      youtubeParams\n      caption\n      contributors {\n        name\n        url\n      }\n    }\n  }\n\n  fragment shortcodeSpotifyFragment on ShortcodeInterface {\n    ... on ShortcodeSpotifyGQL {\n      uri\n      compact\n      pos\n      size\n    }\n  }\n\n  fragment shortcodeSoundFragment on ShortcodeInterface {\n    ... on ShortcodeSoundGQL {\n      url\n      pos\n      size\n      id\n    }\n  }\n\n  fragment shortcodeBoxQuoteFragment on ShortcodeInterface {\n    ... on ShortcodeBoxQuoteGQL {\n      text\n      imageUrl\n\n      speaker\n      description\n\n      relContent {\n        imgUrl(width: 600, height: 600)\n        url\n        title\n      }\n    }\n  }\n\n  fragment shortcodeDropcapFragment on ShortcodeInterface {\n    ... on ShortcodeDropcapGQL {\n      text\n      color\n    }\n  }\n\n  fragment shortcodeDocumentCloudFragment on ShortcodeInterface {\n    ... on ShortcodeDocumentCloudGQL {\n      documentId\n      noteId\n    }\n  }\n\n  fragment shortcodeExtContFragment on ShortcodeInterface {\n    ... on ShortcodeExtContGQL {\n      link\n      imageUrl\n      contributors {\n        name\n        url\n      }\n      caption\n    }\n  }\n\n  fragment shortcodeFlashGraphicFragment on ShortcodeInterface {\n    ... on ShortcodeFlashGraphicGQL {\n      flashGraphic {\n        graphicUrl\n        width\n        height\n      }\n      height\n      caption\n      contributors {\n        name\n        url\n      }\n    }\n  }\n\n  fragment shortcodeGalleryFragment on ShortcodeInterface {\n    ... on ShortcodeGalleryGQL {\n      contributors {\n        name\n        url\n      }\n      caption\n      pos\n      size\n      images {\n        imgUrl(width: 1500, height: 1500)\n        title\n        description\n      }\n    }\n  }\n\n  fragment shortcodePdfFragment on ShortcodeInterface {\n    ... on ShortcodePdfGQL {\n      pdf {\n        documentUrl\n        contributors {\n          name\n          url\n        }\n      }\n      pos\n      size\n      height\n      byline\n      caption\n    }\n  }\n\n  fragment shortcodeWidgetFragment on ShortcodeInterface {\n    ... on ShortcodeWidgetGQL {\n      widget {\n        html\n        javascript\n        isHighcharts\n        isD3\n      }\n      pos\n      size\n      caption\n      contributors {\n        name\n        url\n      }\n    }\n  }\n\n  fragment shortcodeTextEffectFragment on ShortcodeInterface {\n    ... on ShortcodeTextEffectGQL {\n      text\n      effect\n    }\n  }\n\n  fragment shortcodeImageFadeInFragment on ShortcodeInterface {\n    ... on ShortcodeImageFadeInGQL {\n      imageUrl\n    }\n  }\n\n  fragment shortcodeGoogleFormFragment on ShortcodeInterface {\n    ... on ShortcodeGoogleFormGQL {\n      id\n      size\n      pos\n      height\n    }\n  }\n\n  fragment shortcodePreviewFragment on ShortcodeInterface {\n    ... on ShortcodePreviewGQL {\n      phrase\n      desc\n      link\n      highlight\n      imageUrl\n    }\n  }\n\n  fragment shortcodeSponsorFragment on ShortcodeInterface {\n    ... on ShortcodeSponsorGQL {\n      imageUrl\n      size\n      name\n      link\n      prefix\n    }\n  }\n\n  fragment shortcodeTweetFragment on ShortcodeInterface {\n    ... on ShortcodeTweetGQL {\n      id\n      pos\n      size\n    }\n  }\n"
    }
    gql_json = utils.post_url('https://api.thecrimson.com/graphql', json_data=gql_query)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    content_json = gql_json['data']['content']

    item = {}
    item['id'] = content_json['url']
    item['url'] = 'https://www.thecrimson.com' + content_json['url']
    item['title'] = content_json['title']

    dt = datetime.fromisoformat(content_json['createdOn'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(content_json['modifiedOn'])
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in content_json['contributors']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if content_json.get('tags'):
        item['tags'] = []
        for it in content_json['tags']:
            item['tags'].append(it['text'])

    item['content_html'] = ''
    if content_json.get('subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(content_json['subtitle'])

    if content_json.get('mainContent'):
        if content_json['mainContent']['__typename'] == 'ImageGQL':
            item['_image'] = content_json['mainContent']['imgUrl']
            shortcode = None
            if content_json.get('paragraphs'):
                m = re.search(r'\{shortcode-[0-9a-f]+\}', content_json['paragraphs'][0])
                if m:
                    shortcode = next((it for it in content_json['shortcodes'] if it['key'] == m.group(0)), None)
                    if shortcode and shortcode == 'ShortcodeDropcapGQL':
                        shortcode = None
            if not shortcode:
                captions = []
                if content_json['mainContent'].get('caption'):
                    captions.append(content_json['mainContent']['caption'])
                if content_json['mainContent'].get('contributors'):
                    authors = []
                    for it in content_json['mainContent']['contributors']:
                        authors.append(it['name'])
                    if authors:
                        captions.append('By ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)))
                item['content_html'] += utils.add_image(content_json['mainContent']['imgUrl'], ' | '.join(captions))
        elif content_json['mainContent']['__typename'] == 'VideoGQL':
            media_item = utils.get_content('https://www.youtube.com/watch?v=' + content_json['mainContent']['videoId'], {"embed": True}, False)
            if media_item:
                item['_image'] = media_item['_image']
                item['content_html'] += media_item['content_html']
            else:
                logger.warning('unhandled mainContent VideoGQL in' + item['url'])
        else:
            logger.warning('unhandled mainContent type {} in {}'.format(content_json['mainContent']['__typename'], item['url']))

    if content_json.get('paragraphs'):
        for paragraph in content_json['paragraphs']:
            m = re.search(r'\{shortcode-[0-9a-f]+\}', paragraph)
            if m:
                shortcode = next((it for it in content_json['shortcodes'] if it['key'] == m.group(0)), None)
                if shortcode:
                    if shortcode['__typename'] == 'ShortcodeImageGQL':
                        captions = []
                        if shortcode.get('caption'):
                            captions.append(shortcode['caption'])
                        if shortcode.get('contributors'):
                            authors = []
                            for it in shortcode['contributors']:
                                authors.append(it['name'])
                            if authors:
                                captions.append('By ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)))
                        item['content_html'] += utils.add_image(shortcode['imageUrl'], ' | '.join(captions))
                    elif shortcode['__typename'] == 'ShortcodeGalleryGQL':
                        captions = []
                        if shortcode.get('caption') and shortcode['caption'] != 'true':
                            captions.append(shortcode['caption'])
                        if shortcode.get('contributors'):
                            authors = []
                            for it in shortcode['contributors']:
                                authors.append(it['name'])
                            if authors:
                                captions.append('By ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)))
                        for it in shortcode['images']:
                            caption = ' | '.join(captions)
                            if it.get('title'):
                                if caption:
                                    caption = it['title'] + ' | ' + caption
                                else:
                                    caption = it['title']
                            item['content_html'] += utils.add_image(it['imgUrl'], caption)
                    elif shortcode['__typename'] == 'ShortcodeYoutubeGQL':
                        item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v=' + shortcode['videoId'])
                    elif shortcode['__typename'] == 'ShortcodeTweetGQL':
                        item['content_html'] += utils.add_embed('https://twitter.com/__/status/' + shortcode['id'])
                    elif shortcode['__typename'] == 'ShortcodeWidgetGQL':
                        new_para = ''
                        if shortcode['widget']['html'].startswith('<iframe'):
                            m = re.search(r'src="([^"]+)"', shortcode['widget']['html'])
                            if m:
                                new_para = utils.add_embed(m.group(1))
                        elif 'flourish-embed' in shortcode['widget']['html']:
                            m = re.search(r'data-src="([^"]+)"', shortcode['widget']['html'])
                            if m:
                                src = 'https://flo.uri.sh/{}/embed'.format(m.group(1))
                                img = '{}/screenshot?url={}&locator=%23fl-layout-wrapper-outer'.format(config.server, quote_plus(src))
                                new_para = utils.add_image(img, link=src)
                        if new_para:
                            item['content_html'] += new_para
                        else:
                            logger.warning('unhandled ShortcodeWidgetGQL in ' + item['url'])
                    elif shortcode['__typename'] == 'ShortcodePdfGQL':
                        item['content_html'] += utils.add_embed('https://drive.google.com/viewerng/viewer?url=' + quote_plus(shortcode['pdf']['documentUrl']))
                    elif shortcode['__typename'] == 'ShortcodeDropcapGQL':
                        item['content_html'] += paragraph.replace(m.group(0), '<span style="float:left; font-size:4em; line-height:0.8em;">{}</span>'.format(shortcode['text'])) + '<div style="float:clear;"></div>'
                    else:
                        logger.warning('unhandled shortcode type {} in {}'.format(shortcode['__typename'], item['url']))
                        item['content_html'] += paragraph
                else:
                    logger.warning('unknown shortcode {} in {}'.format(m.group(0), item['url']))
                    item['content_html'] += paragraph
            else:
                item['content_html'] += paragraph

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'feeds' in paths:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    articles = []
    feed_title = ''
    if len(paths) == 0:
        gql_query = {
            "operationName": "GetReaderHeaderIndex",
            "variables": {},
            "query": "\n  query GetReaderHeaderIndex {\n    redHeaderIndex {\n      primaryFirstFeatured         { ...mediumImagePlaceholder }\n      primarySecondFeatured        { ...mediumImagePlaceholder }\n      primaryFirst                 { ...mediumImagePlaceholder }\n      primarySecond                { ...mediumImagePlaceholder }\n      primaryFirstBottom           { ...mediumImagePlaceholder }\n      primarySecondColumns         { ...mediumImagePlaceholder }\n      opinion                      { ...mediumImagePlaceholder }\n      fmFeatured                   { ...mediumImagePlaceholder }\n      artsSection                  { ...mediumImagePlaceholder }\n      sportsSecondSection          { ...mediumImagePlaceholder }\n      sportsFeaturedSection        { ...mediumImagePlaceholder }\n    }\n  }\n  \n    fragment mediumImagePlaceholder on PlaceholderGQL {\n      ...basePlaceholderFragment\n      content {\n        imgUrl(width: 550, height: 356)\n      }\n    }\n\n    \n  fragment basePlaceholderFragment on PlaceholderGQL {\n    title\n    content {\n      ...contentFragment\n    }\n  }\n\n  \n  fragment contentFragment on ContentGQL {\n    __typename\n    title\n    subtitle\n    description\n    contributorOverride\n    createdOn\n    modifiedOn\n    showAds\n    searchable\n    slug\n    url\n\n    group {\n      name\n      # TODO: add the rest of the ContentGroup fields as needed\n    }\n\n    contributors {\n      name\n      url\n    }\n\n    multimediaContributors {\n      name\n      url\n    }\n\n    tags {\n      text\n      url\n    }\n\n    issue {\n      issueDate\n    }\n\n    section {\n      name\n    }\n\n    subsection {\n      text\n      url\n    }\n\n    fmSubsection\n\n    flybySubsection\n\n    relContent {\n      title\n      url\n      contributors {\n        name\n        url\n      }\n\n      # NOTE: imgUrl should be queried for on a case by case\n      # basis to prevent the download of unnecessarily large images\n      # imgUrl(width: xxx, height: xxx)\n    }\n\n    mainContent {\n      __typename\n      description\n      contributors {\n        name\n        url\n      }\n      ... on ImageGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on FlashGraphicGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on GalleryGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on VideoGQL {\n        videoId\n      }\n    }\n\n    # NOTE: imgUrl should be queried for on a case by case\n    # basis to prevent the download of unnecessarily large images\n    # imgUrl(width: xxx, height: xxx)\n\n    # other generic content fields that we probably won't use:\n    # slug\n    # priority\n    # searchable\n    # paginate\n    # numComments\n    # frontpage\n  }\n"
        }
        gql_json = utils.post_url('https://api.thecrimson.com/graphql', json_data=gql_query)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        for key, val in gql_json['data']['redHeaderIndex'].items():
            if val.get('content'):
                articles += val['content']
        feed_title = 'The Harvard Crimson'
    elif paths[0] == 'section':
        if paths[-1] == 'news':
            gql_query = {
                "operationName": "GetNewsLayoutInstance",
                "variables": {},
                "query": "\n  query GetNewsLayoutInstance {\n    newsLayoutInstance {\n      topFeatured {\n        ...mediumImagePlaceholder\n      }\n\n      cardFeatures {\n        ...mediumImagePlaceholder\n      }\n\n      rowFeatures {\n        ...mediumImagePlaceholder\n      }\n    }\n  }\n  \n    fragment mediumImagePlaceholder on PlaceholderGQL {\n      ...basePlaceholderFragment\n      content {\n        imgUrl(width: 550, height: 356)\n      }\n    }\n\n    \n  fragment basePlaceholderFragment on PlaceholderGQL {\n    title\n    content {\n      ...contentFragment\n    }\n  }\n\n  \n  fragment contentFragment on ContentGQL {\n    __typename\n    title\n    subtitle\n    description\n    contributorOverride\n    createdOn\n    modifiedOn\n    showAds\n    searchable\n    slug\n    url\n\n    group {\n      name\n      # TODO: add the rest of the ContentGroup fields as needed\n    }\n\n    contributors {\n      name\n      url\n    }\n\n    multimediaContributors {\n      name\n      url\n    }\n\n    tags {\n      text\n      url\n    }\n\n    issue {\n      issueDate\n    }\n\n    section {\n      name\n    }\n\n    subsection {\n      text\n      url\n    }\n\n    fmSubsection\n\n    flybySubsection\n\n    relContent {\n      title\n      url\n      contributors {\n        name\n        url\n      }\n\n      # NOTE: imgUrl should be queried for on a case by case\n      # basis to prevent the download of unnecessarily large images\n      # imgUrl(width: xxx, height: xxx)\n    }\n\n    mainContent {\n      __typename\n      description\n      contributors {\n        name\n        url\n      }\n      ... on ImageGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on FlashGraphicGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on GalleryGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on VideoGQL {\n        videoId\n      }\n    }\n\n    # NOTE: imgUrl should be queried for on a case by case\n    # basis to prevent the download of unnecessarily large images\n    # imgUrl(width: xxx, height: xxx)\n\n    # other generic content fields that we probably won't use:\n    # slug\n    # priority\n    # searchable\n    # paginate\n    # numComments\n    # frontpage\n  }\n"
            }
            feed_title = 'News | The Harvard Crimson'
        elif paths[-1] == 'opinion':
            gql_query = {
                "operationName": "GetOpinionLayoutInstance",
                "variables": {},
                "query": "\n  query GetOpinionLayoutInstance {\n    opinionLayoutInstance {\n      recent {\n        ...mediumImagePlaceholder\n      }\n      editorials {\n        ...mediumImagePlaceholder\n      }\n      opeds {\n        ...mediumImagePlaceholder\n      }\n    }\n\n    currentColumns(section: \"opinion\") {\n      ...columnFragment\n    }\n\n    columnArticles(section: \"opinion\", num: 3) {\n      ...contentFragment\n    }\n  }\n  \n    fragment mediumImagePlaceholder on PlaceholderGQL {\n      ...basePlaceholderFragment\n      content {\n        imgUrl(width: 550, height: 356)\n      }\n    }\n\n    \n  fragment basePlaceholderFragment on PlaceholderGQL {\n    title\n    content {\n      ...contentFragment\n    }\n  }\n\n  \n  fragment contentFragment on ContentGQL {\n    __typename\n    title\n    subtitle\n    description\n    contributorOverride\n    createdOn\n    modifiedOn\n    showAds\n    searchable\n    slug\n    url\n\n    group {\n      name\n      # TODO: add the rest of the ContentGroup fields as needed\n    }\n\n    contributors {\n      name\n      url\n    }\n\n    multimediaContributors {\n      name\n      url\n    }\n\n    tags {\n      text\n      url\n    }\n\n    issue {\n      issueDate\n    }\n\n    section {\n      name\n    }\n\n    subsection {\n      text\n      url\n    }\n\n    fmSubsection\n\n    flybySubsection\n\n    relContent {\n      title\n      url\n      contributors {\n        name\n        url\n      }\n\n      # NOTE: imgUrl should be queried for on a case by case\n      # basis to prevent the download of unnecessarily large images\n      # imgUrl(width: xxx, height: xxx)\n    }\n\n    mainContent {\n      __typename\n      description\n      contributors {\n        name\n        url\n      }\n      ... on ImageGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on FlashGraphicGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on GalleryGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on VideoGQL {\n        videoId\n      }\n    }\n\n    # NOTE: imgUrl should be queried for on a case by case\n    # basis to prevent the download of unnecessarily large images\n    # imgUrl(width: xxx, height: xxx)\n\n    # other generic content fields that we probably won't use:\n    # slug\n    # priority\n    # searchable\n    # paginate\n    # numComments\n    # frontpage\n  }\n\n  fragment columnFragment on ContentGroupGQL {\n    name\n    imgUrl\n    contributors {\n      name\n      url\n    }\n    lastPublished\n    url\n  }\n"
            }
            feed_title = 'Opinion | The Harvard Crimson'
        elif paths[-1] == 'arts':
            gql_query = {
                "operationName": "GetArtsLayoutInstance",
                "variables": {},
                "query": "\n  query GetArtsLayoutInstance {\n    artsLayoutInstance {\n      recent {\n        ...mediumImagePlaceholder\n      }\n      oncampus {\n        ...mediumImagePlaceholder\n      }\n    }\n\n    currentColumns(section: \"arts\") {\n      ...columnFragment\n    }\n\n    columnArticles(section: \"arts\", num: 2) {\n      title\n      contributors {\n        name\n        url\n      }\n      description\n      url\n      imgUrl(width: 600, height: 400)\n      issue {\n        issueDate\n      }\n    }\n  }\n  \n    fragment mediumImagePlaceholder on PlaceholderGQL {\n      ...basePlaceholderFragment\n      content {\n        imgUrl(width: 550, height: 356)\n      }\n    }\n\n    \n  fragment basePlaceholderFragment on PlaceholderGQL {\n    title\n    content {\n      ...contentFragment\n    }\n  }\n\n  \n  fragment contentFragment on ContentGQL {\n    __typename\n    title\n    subtitle\n    description\n    contributorOverride\n    createdOn\n    modifiedOn\n    showAds\n    searchable\n    slug\n    url\n\n    group {\n      name\n      # TODO: add the rest of the ContentGroup fields as needed\n    }\n\n    contributors {\n      name\n      url\n    }\n\n    multimediaContributors {\n      name\n      url\n    }\n\n    tags {\n      text\n      url\n    }\n\n    issue {\n      issueDate\n    }\n\n    section {\n      name\n    }\n\n    subsection {\n      text\n      url\n    }\n\n    fmSubsection\n\n    flybySubsection\n\n    relContent {\n      title\n      url\n      contributors {\n        name\n        url\n      }\n\n      # NOTE: imgUrl should be queried for on a case by case\n      # basis to prevent the download of unnecessarily large images\n      # imgUrl(width: xxx, height: xxx)\n    }\n\n    mainContent {\n      __typename\n      description\n      contributors {\n        name\n        url\n      }\n      ... on ImageGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on FlashGraphicGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on GalleryGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on VideoGQL {\n        videoId\n      }\n    }\n\n    # NOTE: imgUrl should be queried for on a case by case\n    # basis to prevent the download of unnecessarily large images\n    # imgUrl(width: xxx, height: xxx)\n\n    # other generic content fields that we probably won't use:\n    # slug\n    # priority\n    # searchable\n    # paginate\n    # numComments\n    # frontpage\n  }\n\n  fragment columnFragment on ContentGroupGQL {\n    name\n    imgUrl\n    contributors {\n      name\n      url\n    }\n    lastPublished\n    url\n  }\n"
            }
            feed_title = 'Arts | The Harvard Crimson'
        elif paths[-1] == 'features':
            gql_query = {
                "operationName": "GetFeaturesSectionLayoutInstance",
                "variables": {},
                "query": "\n  query GetFeaturesSectionLayoutInstance {\n    featuresSectionLayoutInstance {\n      layoutName\n      layoutId\n    }\n  }\n"
            }
            gql_json = utils.post_url('https://api.thecrimson.com/graphql', json_data=gql_query)
            if not gql_json:
                return None
            gql_query = {
                "operationName": "GetFeaturesTopicPage",
                "variables": {
                    "id": gql_json['data']['featuresSectionLayoutInstance']['layoutId']
                },
                "query": "\n  query GetFeaturesTopicPage($id: Int!) {\n    featuresTopicPage(id: $id) {\n      featured            { ...squareImagePlaceholder }\n      featured2           { ...squareImagePlaceholder }\n      featured3           { ...squareImagePlaceholder }\n      featured4           { ...squareImagePlaceholder }\n    }\n  }\n  \n    fragment squareImagePlaceholder on PlaceholderGQL {\n      ...basePlaceholderFragment\n      content {\n        imgUrl(width: 600, height: 600)\n      }\n    }\n\n    \n  fragment basePlaceholderFragment on PlaceholderGQL {\n    title\n    content {\n      ...contentFragment\n    }\n  }\n\n  \n  fragment contentFragment on ContentGQL {\n    __typename\n    title\n    subtitle\n    description\n    contributorOverride\n    createdOn\n    modifiedOn\n    showAds\n    searchable\n    slug\n    url\n\n    group {\n      name\n      # TODO: add the rest of the ContentGroup fields as needed\n    }\n\n    contributors {\n      name\n      url\n    }\n\n    multimediaContributors {\n      name\n      url\n    }\n\n    tags {\n      text\n      url\n    }\n\n    issue {\n      issueDate\n    }\n\n    section {\n      name\n    }\n\n    subsection {\n      text\n      url\n    }\n\n    fmSubsection\n\n    flybySubsection\n\n    relContent {\n      title\n      url\n      contributors {\n        name\n        url\n      }\n\n      # NOTE: imgUrl should be queried for on a case by case\n      # basis to prevent the download of unnecessarily large images\n      # imgUrl(width: xxx, height: xxx)\n    }\n\n    mainContent {\n      __typename\n      description\n      contributors {\n        name\n        url\n      }\n      ... on ImageGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on FlashGraphicGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on GalleryGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on VideoGQL {\n        videoId\n      }\n    }\n\n    # NOTE: imgUrl should be queried for on a case by case\n    # basis to prevent the download of unnecessarily large images\n    # imgUrl(width: xxx, height: xxx)\n\n    # other generic content fields that we probably won't use:\n    # slug\n    # priority\n    # searchable\n    # paginate\n    # numComments\n    # frontpage\n  }\n"
            }
            feed_title = 'Features | The Harvard Crimson'
        elif paths[-1] == 'fm':
            gql_query = {
                "operationName": "GetFMLandingPage",
                "variables": {},
                "query": "\n  query GetFMLandingPage {\n    fmLayoutInstance {\n      featured {\n        content {\n          title\n          description\n          url\n          imgUrl(height: 2000, width: 2000)\n          contributors {\n            name\n            url\n          }\n        }\n      }\n      alsoInIssue {\n        content {\n          title\n          description\n          fmSubsection\n          url\n          imgUrl(height: 400, width: 400)\n          contributors {\n            name\n            url\n          }\n        }\n      }\n    }\n    scrutiny: magazineArticles(subsection: \"cover-story\", limit: 4) {\n      ...fmFragment\n    }\n    retrospection: magazineArticles(subsection: \"retrospection\", limit: 4) {\n      ...fmFragment\n    }\n    scoop: magazineArticles(subsection: \"the-scoop\", limit: 4) {\n      ...fmFragment\n    }\n    aroundTown: magazineArticles(subsection: \"around-town\", limit: 4) {\n      ...fmFragment\n    }\n    conversations: magazineArticles(subsection: \"conversations\", limit: 4) {\n      ...fmFragment\n    }\n    introspection: magazineArticles(subsection: \"introspection\", limit: 4) {\n      ...fmFragment\n    }\n    levity: magazineArticles(subsection: \"levity\", limit: 4) {\n      ...fmFragment\n    }\n    inquiry: magazineArticles(subsection: \"inquiry\", limit: 4) {\n      ...fmFragment\n    }\n\n    fmCurrentIssue {\n      slug\n    }\n  }\n\n  fragment fmFragment on ArticleGQL {\n    title\n    url\n    fmSubsection\n    contributors {\n      name\n      url\n    }\n    imgUrl(height: 400, width: 400)\n  }\n"
            }
            feed_title = 'Fifteen Minutes Magazine | The Harvard Crimson'
        elif paths[-1] == 'sports':
            gql_query = {
                "operationName": "GetSportsLayoutInstance",
                "variables": {},
                "query": "\n  query GetSportsLayoutInstance {\n    sportsLayoutInstance {\n      top {\n        ...mediumImagePlaceholder\n      }\n\n      middle {\n        ...mediumImagePlaceholder\n      }\n\n      bottom {\n        ...mediumImagePlaceholder\n      }\n    }\n\n    columnArticles(section: \"sports\", num: 3) {\n      ...contentFragment\n    }\n\n    currentColumns(section: \"sports\") {\n      ...columnFragment\n    }\n  }\n  \n    fragment mediumImagePlaceholder on PlaceholderGQL {\n      ...basePlaceholderFragment\n      content {\n        imgUrl(width: 550, height: 356)\n      }\n    }\n\n    \n  fragment basePlaceholderFragment on PlaceholderGQL {\n    title\n    content {\n      ...contentFragment\n    }\n  }\n\n  \n  fragment contentFragment on ContentGQL {\n    __typename\n    title\n    subtitle\n    description\n    contributorOverride\n    createdOn\n    modifiedOn\n    showAds\n    searchable\n    slug\n    url\n\n    group {\n      name\n      # TODO: add the rest of the ContentGroup fields as needed\n    }\n\n    contributors {\n      name\n      url\n    }\n\n    multimediaContributors {\n      name\n      url\n    }\n\n    tags {\n      text\n      url\n    }\n\n    issue {\n      issueDate\n    }\n\n    section {\n      name\n    }\n\n    subsection {\n      text\n      url\n    }\n\n    fmSubsection\n\n    flybySubsection\n\n    relContent {\n      title\n      url\n      contributors {\n        name\n        url\n      }\n\n      # NOTE: imgUrl should be queried for on a case by case\n      # basis to prevent the download of unnecessarily large images\n      # imgUrl(width: xxx, height: xxx)\n    }\n\n    mainContent {\n      __typename\n      description\n      contributors {\n        name\n        url\n      }\n      ... on ImageGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on FlashGraphicGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on GalleryGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on VideoGQL {\n        videoId\n      }\n    }\n\n    # NOTE: imgUrl should be queried for on a case by case\n    # basis to prevent the download of unnecessarily large images\n    # imgUrl(width: xxx, height: xxx)\n\n    # other generic content fields that we probably won't use:\n    # slug\n    # priority\n    # searchable\n    # paginate\n    # numComments\n    # frontpage\n  }\n\n  fragment columnFragment on ContentGroupGQL {\n    name\n    imgUrl\n    contributors {\n      name\n      url\n    }\n    lastPublished\n    url\n  }\n"
            }
            feed_title = 'Sports | The Harvard Crimson'
        elif paths[-1] == 'media':
            gql_query = {
                "operationName": "GetMultiLayoutInstance",
                "variables": {},
                "query": "\n  query GetMultiLayoutInstance {\n    multimediaLayoutInstance {\n      featuredPhotos {\n        ...mediumImagePlaceholder\n      }\n    }\n\n    photoEssays {\n      ...contentFragment\n      imgUrl(width: 400, height: 400)\n    }\n\n    recentVideos {\n      imgUrl(width: 400, height: 400)\n      url\n      title\n    }\n  }\n  \n    fragment mediumImagePlaceholder on PlaceholderGQL {\n      ...basePlaceholderFragment\n      content {\n        imgUrl(width: 550, height: 356)\n      }\n    }\n\n    \n  fragment basePlaceholderFragment on PlaceholderGQL {\n    title\n    content {\n      ...contentFragment\n    }\n  }\n\n  \n  fragment contentFragment on ContentGQL {\n    __typename\n    title\n    subtitle\n    description\n    contributorOverride\n    createdOn\n    modifiedOn\n    showAds\n    searchable\n    slug\n    url\n\n    group {\n      name\n      # TODO: add the rest of the ContentGroup fields as needed\n    }\n\n    contributors {\n      name\n      url\n    }\n\n    multimediaContributors {\n      name\n      url\n    }\n\n    tags {\n      text\n      url\n    }\n\n    issue {\n      issueDate\n    }\n\n    section {\n      name\n    }\n\n    subsection {\n      text\n      url\n    }\n\n    fmSubsection\n\n    flybySubsection\n\n    relContent {\n      title\n      url\n      contributors {\n        name\n        url\n      }\n\n      # NOTE: imgUrl should be queried for on a case by case\n      # basis to prevent the download of unnecessarily large images\n      # imgUrl(width: xxx, height: xxx)\n    }\n\n    mainContent {\n      __typename\n      description\n      contributors {\n        name\n        url\n      }\n      ... on ImageGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on FlashGraphicGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on GalleryGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on VideoGQL {\n        videoId\n      }\n    }\n\n    # NOTE: imgUrl should be queried for on a case by case\n    # basis to prevent the download of unnecessarily large images\n    # imgUrl(width: xxx, height: xxx)\n\n    # other generic content fields that we probably won't use:\n    # slug\n    # priority\n    # searchable\n    # paginate\n    # numComments\n    # frontpage\n  }\n"
            }
            feed_title = 'Multimedia | The Harvard Crimson'
        gql_json = utils.post_url('https://api.thecrimson.com/graphql', json_data=gql_query)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        for key, val in gql_json['data'].items():
            if key == 'currentColumns' or key == 'fmCurrentIssue':
                continue
            elif isinstance(val, list):
                articles += val
            elif isinstance(val, dict):
                for k, v in val.items():
                    if v.get('content'):
                        articles += v['content']
    elif paths[0] == 'tag':
        gql_query = {
            "operationName": "GetTagArticles",
            "variables": {
                "tagName": paths[1],
                "pageNum": 1
            },
            "query": "\n  query GetTagArticles($tagName: String!, $pageNum: Int) {\n    tagPage(tagName: $tagName, pageNum: $pageNum) {\n      tag {\n        text\n        url\n      }\n      content {\n        ...contentFragment\n        imgUrl(width: 200, height: 200)\n      }\n      paginator {\n        currPage\n        totalItems\n        pageSize\n      }\n    }\n  }\n  \n  fragment contentFragment on ContentGQL {\n    __typename\n    title\n    subtitle\n    description\n    contributorOverride\n    createdOn\n    modifiedOn\n    showAds\n    searchable\n    slug\n    url\n\n    group {\n      name\n      # TODO: add the rest of the ContentGroup fields as needed\n    }\n\n    contributors {\n      name\n      url\n    }\n\n    multimediaContributors {\n      name\n      url\n    }\n\n    tags {\n      text\n      url\n    }\n\n    issue {\n      issueDate\n    }\n\n    section {\n      name\n    }\n\n    subsection {\n      text\n      url\n    }\n\n    fmSubsection\n\n    flybySubsection\n\n    relContent {\n      title\n      url\n      contributors {\n        name\n        url\n      }\n\n      # NOTE: imgUrl should be queried for on a case by case\n      # basis to prevent the download of unnecessarily large images\n      # imgUrl(width: xxx, height: xxx)\n    }\n\n    mainContent {\n      __typename\n      description\n      contributors {\n        name\n        url\n      }\n      ... on ImageGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on FlashGraphicGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on GalleryGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on VideoGQL {\n        videoId\n      }\n    }\n\n    # NOTE: imgUrl should be queried for on a case by case\n    # basis to prevent the download of unnecessarily large images\n    # imgUrl(width: xxx, height: xxx)\n\n    # other generic content fields that we probably won't use:\n    # slug\n    # priority\n    # searchable\n    # paginate\n    # numComments\n    # frontpage\n  }\n"
        }
        gql_json = utils.post_url('https://api.thecrimson.com/graphql', json_data=gql_query)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        articles = gql_json['data']['tagPage']['content']
        feed_title = '{} | The Harvard Crimson'.format(gql_json['data']['tagPage']['tag']['text'])
    elif paths[0] == 'flyby':
        if len(paths) == 1:
            gql_query = {
                "operationName": "GetFlybyArticles",
                "variables": {
                    "offset": 0,
                    "limit": 10
                },
                "query": "\n  query GetFlybyArticles($offset: Int!, $limit: Int!) {\n    flybyContent(offset: $offset, limit: $limit) {\n      ...contentFragment\n      imgUrl(width: 500, height: 500)\n    }\n  }\n  \n  fragment contentFragment on ContentGQL {\n    __typename\n    title\n    subtitle\n    description\n    contributorOverride\n    createdOn\n    modifiedOn\n    showAds\n    searchable\n    slug\n    url\n\n    group {\n      name\n      # TODO: add the rest of the ContentGroup fields as needed\n    }\n\n    contributors {\n      name\n      url\n    }\n\n    multimediaContributors {\n      name\n      url\n    }\n\n    tags {\n      text\n      url\n    }\n\n    issue {\n      issueDate\n    }\n\n    section {\n      name\n    }\n\n    subsection {\n      text\n      url\n    }\n\n    fmSubsection\n\n    flybySubsection\n\n    relContent {\n      title\n      url\n      contributors {\n        name\n        url\n      }\n\n      # NOTE: imgUrl should be queried for on a case by case\n      # basis to prevent the download of unnecessarily large images\n      # imgUrl(width: xxx, height: xxx)\n    }\n\n    mainContent {\n      __typename\n      description\n      contributors {\n        name\n        url\n      }\n      ... on ImageGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on FlashGraphicGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on GalleryGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on VideoGQL {\n        videoId\n      }\n    }\n\n    # NOTE: imgUrl should be queried for on a case by case\n    # basis to prevent the download of unnecessarily large images\n    # imgUrl(width: xxx, height: xxx)\n\n    # other generic content fields that we probably won't use:\n    # slug\n    # priority\n    # searchable\n    # paginate\n    # numComments\n    # frontpage\n  }\n"
            }
        else:
            gql_query = {
                "operationName": "GetFlybySubsection",
                "variables": {
                    "subsection": paths[1],
                    "offset": 0,
                    "limit": 10
                },
                "query": "\n  query GetFlybySubsection($subsection: String!, $offset: Int!, $limit: Int!) {\n    flybyContent(offset: $offset, limit: $limit, subsection: $subsection) {\n      ...contentFragment\n      imgUrl(width: 500, height: 500)\n    }\n  }\n  \n  fragment contentFragment on ContentGQL {\n    __typename\n    title\n    subtitle\n    description\n    contributorOverride\n    createdOn\n    modifiedOn\n    showAds\n    searchable\n    slug\n    url\n\n    group {\n      name\n      # TODO: add the rest of the ContentGroup fields as needed\n    }\n\n    contributors {\n      name\n      url\n    }\n\n    multimediaContributors {\n      name\n      url\n    }\n\n    tags {\n      text\n      url\n    }\n\n    issue {\n      issueDate\n    }\n\n    section {\n      name\n    }\n\n    subsection {\n      text\n      url\n    }\n\n    fmSubsection\n\n    flybySubsection\n\n    relContent {\n      title\n      url\n      contributors {\n        name\n        url\n      }\n\n      # NOTE: imgUrl should be queried for on a case by case\n      # basis to prevent the download of unnecessarily large images\n      # imgUrl(width: xxx, height: xxx)\n    }\n\n    mainContent {\n      __typename\n      description\n      contributors {\n        name\n        url\n      }\n      ... on ImageGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on FlashGraphicGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on GalleryGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on VideoGQL {\n        videoId\n      }\n    }\n\n    # NOTE: imgUrl should be queried for on a case by case\n    # basis to prevent the download of unnecessarily large images\n    # imgUrl(width: xxx, height: xxx)\n\n    # other generic content fields that we probably won't use:\n    # slug\n    # priority\n    # searchable\n    # paginate\n    # numComments\n    # frontpage\n  }\n"
            }

        gql_json = utils.post_url('https://api.thecrimson.com/graphql', json_data=gql_query)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        articles = gql_json['data']['flybyContent']
        feed_title = 'flyby | The Harvard Crimson'
    elif paths[0] == 'writer':
        gql_query = {
            "operationName": "GetWriterArticles",
            "variables": {
                "id": paths[1],
                "offset": 0,
                "limit": 10
            },
            "query": "\n  query GetWriterArticles($id: Int!, $offset: Int!, $limit: Int!) {\n    contributor(id: $id) {\n      name\n      title\n      bioText\n      imgUrl(width: 600, height: 600)\n      tagline\n      content(offset: $offset, limit: $limit) {\n        ...contentFragment\n        imgUrl(width: 400, height: 400)\n      }\n    }\n  }\n  \n  fragment contentFragment on ContentGQL {\n    __typename\n    title\n    subtitle\n    description\n    contributorOverride\n    createdOn\n    modifiedOn\n    showAds\n    searchable\n    slug\n    url\n\n    group {\n      name\n      # TODO: add the rest of the ContentGroup fields as needed\n    }\n\n    contributors {\n      name\n      url\n    }\n\n    multimediaContributors {\n      name\n      url\n    }\n\n    tags {\n      text\n      url\n    }\n\n    issue {\n      issueDate\n    }\n\n    section {\n      name\n    }\n\n    subsection {\n      text\n      url\n    }\n\n    fmSubsection\n\n    flybySubsection\n\n    relContent {\n      title\n      url\n      contributors {\n        name\n        url\n      }\n\n      # NOTE: imgUrl should be queried for on a case by case\n      # basis to prevent the download of unnecessarily large images\n      # imgUrl(width: xxx, height: xxx)\n    }\n\n    mainContent {\n      __typename\n      description\n      contributors {\n        name\n        url\n      }\n      ... on ImageGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on FlashGraphicGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on GalleryGQL {\n        imgUrl(width: 2000, height: 2000)\n      }\n      ... on VideoGQL {\n        videoId\n      }\n    }\n\n    # NOTE: imgUrl should be queried for on a case by case\n    # basis to prevent the download of unnecessarily large images\n    # imgUrl(width: xxx, height: xxx)\n\n    # other generic content fields that we probably won't use:\n    # slug\n    # priority\n    # searchable\n    # paginate\n    # numComments\n    # frontpage\n  }\n"
        }
        gql_json = utils.post_url('https://api.thecrimson.com/graphql', json_data=gql_query)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/feed.json')
        articles = gql_json['data']['contributor']['content']
        feed_title = '{} | The Harvard Crimson'.format(gql_json['data']['contributor']['name'])


    if articles:
        n = 0
        feed_items = []
        for article in articles:
            if not article.get('url'):
                continue
            article_url = 'https://www.thecrimson.com' + article['url']
            if save_debug:
                logger.debug('getting content for ' + article_url)
            item = get_content(article_url, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

        feed = utils.init_jsonfeed(args)
        if feed_title:
            feed['title'] = feed_title
        feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
