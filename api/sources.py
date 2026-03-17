"""
Nimetyt URL:t API-dokumentaatioihin.
Käyttö: fetch_doc("spotify.search") tai fetch_doc("lastfm.similar_tracks")
"""

DOCS: dict[str, str] = {

    # ─── SPOTIFY ────────────────────────────────────────────────────────────
    # Haku
    "spotify.search":               "https://developer.spotify.com/documentation/web-api/reference/search",

    # Kappaleet
    "spotify.get_track":            "https://developer.spotify.com/documentation/web-api/reference/get-track",
    "spotify.get_several_tracks":   "https://developer.spotify.com/documentation/web-api/reference/get-several-tracks",
    "spotify.audio_features":       "https://developer.spotify.com/documentation/web-api/reference/get-audio-features",
    "spotify.audio_analysis":       "https://developer.spotify.com/documentation/web-api/reference/get-audio-analysis",

    # Artistit
    "spotify.get_artist":           "https://developer.spotify.com/documentation/web-api/reference/get-an-artist",
    "spotify.artist_top_tracks":    "https://developer.spotify.com/documentation/web-api/reference/get-an-artists-top-tracks",
    "spotify.related_artists":      "https://developer.spotify.com/documentation/web-api/reference/get-an-artists-related-artists",

    # Suositukset (DEPRECATED mutta toimii)
    "spotify.recommendations":      "https://developer.spotify.com/documentation/web-api/reference/get-recommendations",
    "spotify.genre_seeds":          "https://developer.spotify.com/documentation/web-api/reference/get-recommendation-genres",

    # Soittolistat
    "spotify.create_playlist":      "https://developer.spotify.com/documentation/web-api/reference/create-playlist",
    "spotify.add_items_to_playlist": "https://developer.spotify.com/documentation/web-api/reference/add-tracks-to-playlist",
    "spotify.get_playlist":         "https://developer.spotify.com/documentation/web-api/reference/get-playlist",
    "spotify.update_playlist":      "https://developer.spotify.com/documentation/web-api/reference/change-playlist-details",

    # Käyttäjä
    "spotify.current_user":         "https://developer.spotify.com/documentation/web-api/reference/get-current-users-profile",
    "spotify.user_playlists":       "https://developer.spotify.com/documentation/web-api/reference/get-a-list-of-current-users-playlists",
    "spotify.remove_playlist_items":"https://developer.spotify.com/documentation/web-api/reference/remove-tracks-playlist",
    "spotify.reorder_playlist":     "https://developer.spotify.com/documentation/web-api/reference/reorder-or-replace-a-playlists-items",
    "spotify.get_playlist_items":   "https://developer.spotify.com/documentation/web-api/reference/get-playlists-items",
    # Kuunteluhistoria
    "spotify.recently_played":      "https://developer.spotify.com/documentation/web-api/reference/get-recently-played",
    "spotify.top_tracks":           "https://developer.spotify.com/documentation/web-api/reference/get-users-top-artists-and-tracks",
    "spotify.top_artists":          "https://developer.spotify.com/documentation/web-api/reference/get-users-top-artists-and-tracks",

    # ─── LAST.FM ────────────────────────────────────────────────────────────
    "lastfm.similar_tracks":        "https://www.last.fm/api/show/track.getSimilar",
    "lastfm.similar_artists":       "https://www.last.fm/api/show/artist.getSimilar",
    "lastfm.artist_top_tracks":     "https://www.last.fm/api/show/artist.getTopTracks",
    "lastfm.artist_tags":           "https://www.last.fm/api/show/artist.getTopTags",
    "lastfm.track_info":            "https://www.last.fm/api/show/track.getInfo",
    "lastfm.tag_top_tracks":        "https://www.last.fm/api/show/tag.getTopTracks",
    "lastfm.tag_top_artists":       "https://www.last.fm/api/show/tag.getTopArtists",
    "lastfm.search_track":          "https://www.last.fm/api/show/track.search",
    "lastfm.search_artist":         "https://www.last.fm/api/show/artist.search",

    # ─── DISCOGS ────────────────────────────────────────────────────────────
    # Discogs docs on SPA — käytetään suoria API-referenssi-URLeja
    "discogs.search":               "https://www.discogs.com/developers/#database-search",
    "discogs.release":              "https://www.discogs.com/developers/#database-release",
    "discogs.artist":               "https://www.discogs.com/developers/#database-artist",
    "discogs.artist_releases":      "https://www.discogs.com/developers/#database-artist-releases",
    "discogs.master":               "https://www.discogs.com/developers/#database-master-release",
    # Discogs REST API suoraan (testattavissa curl:lla)
    "discogs.api_search":           "https://api.discogs.com/database/search",
    "discogs.api_release":          "https://api.discogs.com/releases/249504",
    "discogs.api_artist":           "https://api.discogs.com/artists/45",

    # ─── MUSICBRAINZ ────────────────────────────────────────────────────────
    "musicbrainz.search_recording": "https://musicbrainz.org/doc/MusicBrainz_API/Search#recording",
    "musicbrainz.search_artist":    "https://musicbrainz.org/doc/MusicBrainz_API/Search#artist",
    "musicbrainz.recording":        "https://musicbrainz.org/doc/MusicBrainz_API#Recording",
    "musicbrainz.artist_rels":      "https://musicbrainz.org/doc/Artist_Relationship_Types",

    # ─── LISTENBRAINZ ───────────────────────────────────────────────────────
    "listenbrainz.api_index":       "https://listenbrainz.readthedocs.io/en/latest/users/api/index.html",
    "listenbrainz.similar_artists": "https://listenbrainz.readthedocs.io/en/latest/users/api/recommendations.html",
    "listenbrainz.recordings_for_artist": "https://listenbrainz.readthedocs.io/en/latest/users/api/recordings.html",
    "listenbrainz.user_listens":    "https://listenbrainz.readthedocs.io/en/latest/users/api/listens.html",
    "listenbrainz.stats":           "https://listenbrainz.readthedocs.io/en/latest/users/api/statistics.html",

    # ─── YLE AREENA ─────────────────────────────────────────────────────────
    "yle.search":                   "https://developer.yle.fi/en/index.html",
    "yle.programs":                 "https://developer.yle.fi/tutorial/index.html",
}


def list_keys(prefix: str = "") -> list[str]:
    """Listaa kaikki saatavilla olevat doc-avaimet, optionaalisesti prefiksin mukaan."""
    return [k for k in DOCS if k.startswith(prefix)]
