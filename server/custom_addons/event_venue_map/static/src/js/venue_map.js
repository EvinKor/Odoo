odoo.define('event_venue_map.VenueMap', function (require) {
    'use strict';

    var FormController = require('web.FormController');
    var FormView = require('web.FormView');
    var viewRegistry = require('web.view_registry');

    var VenueMapController = FormController.extend({
        events: _.extend({}, FormController.prototype.events, {
            'click #get-current-location': '_onGetCurrentLocation',
            'click #search-address': '_onSearchAddress',
        }),

        start: function () {
            this._super.apply(this, arguments);
            this._initMap();
        },

        _initMap: function () {
            var self = this;
            var mapContainer = this.$el.find('#venue-map');

            if (mapContainer.length === 0) return;

            // Initialize map (using a simple placeholder for now)
            mapContainer.html('<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%;"><i class="fa fa-map-marker fa-3x text-muted mb-2"></i><span>Map will be loaded here</span><small class="text-muted">Use controls below to set location</small></div>');

            // Load actual map library (OpenStreetMap, Google Maps, etc.)
            this._loadMapLibrary();
        },

        _loadMapLibrary: function () {
            var self = this;

            // For now, we'll use a simple geolocation approach
            // In production, you would integrate with Google Maps, OpenStreetMap, etc.

            if (navigator.geolocation) {
                // Get current location if available
                navigator.geolocation.getCurrentPosition(
                    function(position) {
                        var lat = position.coords.latitude;
                        var lng = position.coords.longitude;

                        // Update the map display
                        self._updateMapDisplay(lat, lng);
                    },
                    function(error) {
                        console.log('Geolocation error:', error);
                    }
                );
            }
        },

        _onGetCurrentLocation: function () {
            var self = this;

            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    function(position) {
                        var lat = position.coords.latitude;
                        var lng = position.coords.longitude;

                        // Update form fields
                        self._updateFormCoordinates(lat, lng);

                        // Update map display
                        self._updateMapDisplay(lat, lng);

                        // Reverse geocode to get address
                        self._reverseGeocode(lat, lng);
                    },
                    function(error) {
                        alert('Unable to get current location: ' + error.message);
                    }
                );
            } else {
                alert('Geolocation is not supported by this browser.');
            }
        },

        _onSearchAddress: function () {
            var venueAddress = this.$el.find('input[name="venue_address"]').val();
            var venueCity = this.$el.find('input[name="venue_city"]').val();
            var venueCountry = this.$el.find('select[name="venue_country_id"] option:selected').text();

            var searchQuery = [venueAddress, venueCity, venueCountry].filter(Boolean).join(', ');

            if (!searchQuery.trim()) {
                alert('Please enter an address to search.');
                return;
            }

            // Simple geocoding (in production, use a proper geocoding service)
            this._geocodeAddress(searchQuery);
        },

        _updateFormCoordinates: function (lat, lng) {
            this.$el.find('input[name="venue_latitude"]').val(lat.toFixed(7));
            this.$el.find('input[name="venue_longitude"]').val(lng.toFixed(7));
        },

        _updateMapDisplay: function (lat, lng) {
            var mapContainer = this.$el.find('#venue-map');
            mapContainer.html('<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%;"><i class="fa fa-map-marker fa-3x text-success mb-2"></i><span>Location Set</span><small class="text-muted">Lat: ' + lat.toFixed(4) + ', Lng: ' + lng.toFixed(4) + '</small></div>');
        },

        _reverseGeocode: function (lat, lng) {
            // Simple reverse geocoding (in production, use a proper service)
            // For now, just show coordinates
            console.log('Reverse geocoding:', lat, lng);
        },

        _geocodeAddress: function (address) {
            // Simple geocoding (in production, use Google Maps API, OpenStreetMap Nominatim, etc.)
            alert('Address search functionality would integrate with a geocoding service here.\n\nSearched for: ' + address);

            // Mock coordinates for demonstration
            var mockLat = 40.7128 + (Math.random() - 0.5) * 0.1;
            var mockLng = -74.0060 + (Math.random() - 0.5) * 0.1;

            this._updateFormCoordinates(mockLat, mockLng);
            this._updateMapDisplay(mockLat, mockLng);
        }
    });

    var VenueMapView = FormView.extend({
        config: _.extend({}, FormView.prototype.config, {
            Controller: VenueMapController,
        }),
    });

    viewRegistry.add('venue_map_form', VenueMapView);

    return VenueMapView;
});