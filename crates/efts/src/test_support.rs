use serde_json::{to_value, Value};

use crate::parse::parse_response;

pub fn parse_response_value(
    data: &Value,
    query: &str,
) -> Result<Value, serde_json::Error> {
    to_value(parse_response(data, query))
}
