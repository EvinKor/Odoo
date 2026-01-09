# Event Venue Map

This module replaces the traditional contact-based venue selection in Odoo Events with a direct address storage system and map-based interface.

## Features

- **Direct Address Storage**: Venue addresses are stored directly in the event record instead of creating separate contact records
- **Map Interface**: Interactive map for selecting venue locations
- **Geolocation Support**: Get current location or search for addresses
- **Backward Compatibility**: Maintains compatibility with existing event displays

## Installation

1. Place this module in your Odoo addons directory
2. Update your module list in Odoo
3. Install the "Event Venue Map" module

## Usage

### Setting Venue for Events

1. Go to **Events → Events** and create or edit an event
2. In the "Venue Location" section, fill in:
   - **Venue Name**: Name of the location (e.g., "Conference Center")
   - **Street Address**: Full street address
   - **City, ZIP Code, Country, State**: Address components
   - **Latitude/Longitude**: Coordinates (can be set via map)

### Using the Map Interface

- **Get Current Location**: Click the crosshairs button to use your current location
- **Search Address**: Click the search button to geocode an address
- **Manual Entry**: Enter coordinates directly

## Technical Details

### New Fields Added

- `venue_name`: Char field for venue name
- `venue_address`: Char field for street address
- `venue_city`: Char field for city
- `venue_zip`: Char field for ZIP code
- `venue_country_id`: Many2one to res.country
- `venue_state_id`: Many2one to res.country.state
- `venue_latitude`: Float for latitude coordinates
- `venue_longitude`: Float for longitude coordinates
- `venue_full_address`: Computed field for complete address display

### Map Integration

The module includes a basic map interface that can be extended to integrate with:
- Google Maps API
- OpenStreetMap
- Mapbox
- Other mapping services

### Display Updates

The event list templates have been updated to display the new venue information instead of the old address_id field.

## Future Enhancements

- Integration with Google Maps API for full geocoding
- Address autocomplete functionality
- Route planning features
- Multiple venue support for multi-day events