# Amazon Cognito Setup

## Environment Variables

No environment variables are needed for this implementation as it uses the amazon-cognito-identity-js SDK directly.

## Cognito Configuration

The application is configured to work with the following Cognito User Pool:

- **User Pool ID**: us-east-1_vpBoYyEss
- **Client ID**: 2vhardprmlfa8rfe4rbm4rin3b
- **Region**: us-east-1

## Setup Steps

1. **Install dependencies**: The `amazon-cognito-identity-js` package has been added to package.json
2. **Test login flow**: Visit `/auth/login` to test the Cognito authentication

## Authentication Flow

1. User enters email and password on login form
2. Credentials sent directly to Cognito using amazon-cognito-identity-js SDK
3. Tokens received and stored locally
4. User redirected to home page

## Token Storage

- **Access Token**: `cognito_access_token`
- **ID Token**: `cognito_id_token`
- **Refresh Token**: `cognito_refresh_token` (if available)

## Logout

Logout clears local tokens and signs out from Cognito, then redirects to login page.

## Features

- Direct authentication (no hosted UI redirects)
- Token refresh handling
- User registration and confirmation
- Password reset functionality
- Secure token storage
