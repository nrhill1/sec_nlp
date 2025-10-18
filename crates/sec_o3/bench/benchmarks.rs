// benches/benchmarks.rs - Performance benchmarks
use criterion::{black_box, criterion_group, criterion_main, Criterion, BenchmarkId};
use sec_o3::{
    corp::normalize_cik,
    parse::{parse_html, parse_json, parse_auto},
};

// ============================================================================
// CIK Operations
// ============================================================================

fn bench_normalize_cik(c: &mut Criterion) {
    let mut group = c.benchmark_group("normalize_cik");

    let test_cases = vec![
        ("short", "320193"),
        ("padded", "0000320193"),
        ("with_prefix", "CIK0000320193"),
        ("with_dashes", "0000-320193"),
    ];

    for (name, cik) in test_cases {
        group.bench_with_input(BenchmarkId::from_parameter(name), cik, |b, cik| {
            b.iter(|| normalize_cik(black_box(cik)));
        });
    }

    group.finish();
}

// ============================================================================
// HTML Parsing
// ============================================================================

fn bench_parse_html(c: &mut Criterion) {
    let mut group = c.benchmark_group("parse_html");

    let small_html = r#"
<!DOCTYPE html>
<html>
<head><title>10-K Filing</title></head>
<body>FORM 10-K</body>
</html>
    "#;

    let medium_html = format!(
        r#"
<!DOCTYPE html>
<html>
<head><title>10-K Filing</title></head>
<body>
<div>FORM 10-K</div>
{}
</body>
</html>
        "#,
        "<p>Lorem ipsum</p>".repeat(100)
    );

    let large_html = format!(
        r#"
<!DOCTYPE html>
<html>
<head><title>10-K Filing</title></head>
<body>
<div>FORM 10-K</div>
{}
</body>
</html>
        "#,
        "<p>Lorem ipsum dolor sit amet</p>".repeat(1000)
    );

    group.bench_function("small_1kb", |b| {
        b.iter(|| parse_html(black_box(small_html)).unwrap());
    });

    group.bench_function("medium_10kb", |b| {
        b.iter(|| parse_html(black_box(&medium_html)).unwrap());
    });

    group.bench_function("large_100kb", |b| {
        b.iter(|| parse_html(black_box(&large_html)).unwrap());
    });

    group.finish();
}

// ============================================================================
// JSON Parsing
// ============================================================================

fn bench_parse_json(c: &mut Criterion) {
    let mut group = c.benchmark_group("parse_json");

    let small_json = r#"{"submissionType":"10-K","cik":"0001234567"}"#;

    let medium_json = format!(
        r#"{{
            "submissionType":"10-K",
            "cik":"0001234567",
            "facts":{{{}}}
        }}"#,
        (0..100).map(|i| format!(r#""field{}":"value{}""#, i, i)).collect::<Vec<_>>().join(",")
    );

    let large_json = format!(
        r#"{{
            "submissionType":"10-K",
            "cik":"0001234567",
            "facts":{{{}}}
        }}"#,
        (0..1000).map(|i| format!(r#""field{}":"value{}""#, i, i)).collect::<Vec<_>>().join(",")
    );

    group.bench_function("small_1kb", |b| {
        b.iter(|| parse_json(black_box(small_json)).unwrap());
    });

    group.bench_function("medium_10kb", |b| {
        b.iter(|| parse_json(black_box(&medium_json)).unwrap());
    });

    group.bench_function("large_100kb", |b| {
        b.iter(|| parse_json(black_box(&large_json)).unwrap());
    });

    group.finish();
}

// ============================================================================
// Auto-detection
// ============================================================================

fn bench_parse_auto(c: &mut Criterion) {
    let mut group = c.benchmark_group("parse_auto");

    let html = r#"<!DOCTYPE html><html><body>FORM 10-K</body></html>"#;
    let json = r#"{"submissionType":"8-K"}"#;
    let text = "CONFORMED SUBMISSION TYPE: 10-Q";

    group.bench_function("html", |b| {
        b.iter(|| parse_auto(black_box(html)).unwrap());
    });

    group.bench_function("json", |b| {
        b.iter(|| parse_auto(black_box(json)).unwrap());
    });

    group.bench_function("text", |b| {
        b.iter(|| parse_auto(black_box(text)).unwrap());
    });

    group.finish();
}

// ============================================================================
// Form Type Inference
// ============================================================================

fn bench_form_type_inference(c: &mut Criterion) {
    use sec_o3::parse::infer::infer_form_type;

    let mut group = c.benchmark_group("form_type_inference");

    let test_cases = vec![
        ("explicit_field", "CONFORMED SUBMISSION TYPE: 10-K"),
        ("json_field", r#"{"submissionType":"8-K"}"#),
        ("form_keyword", "This is a FORM 10-Q filing"),
        ("direct_token", "Filing type is 10-K for this document"),
    ];

    for (name, content) in test_cases {
        group.bench_with_input(BenchmarkId::from_parameter(name), content, |b, content| {
            b.iter(|| infer_form_type(black_box(content)));
        });
    }

    group.finish();
}

// ============================================================================
// String Operations
// ============================================================================

fn bench_string_operations(c: &mut Criterion) {
    let mut group = c.benchmark_group("string_operations");

    // Benchmark string allocation patterns
    group.bench_function("format_cik", |b| {
        b.iter(|| format!("{:0>10}", black_box("320193")));
    });

    group.bench_function("string_filter_digits", |b| {
        b.iter(|| {
            let s = "CIK-0000-320193";
            s.chars().filter(|c| c.is_ascii_digit()).collect::<String>()
        });
    });

    group.bench_function("to_uppercase", |b| {
        b.iter(|| black_box("aapl").to_uppercase());
    });

    group.finish();
}

// ============================================================================
// Throughput Benchmarks
// ============================================================================

fn bench_throughput(c: &mut Criterion) {
    let mut group = c.benchmark_group("throughput");
    group.sample_size(50);

    // Batch CIK normalization
    let ciks: Vec<String> = (0..1000).map(|i| i.to_string()).collect();

    group.bench_function("normalize_1000_ciks", |b| {
        b.iter(|| {
            for cik in &ciks {
                black_box(normalize_cik(black_box(cik)));
            }
        });
    });

    // Batch HTML parsing
    let htmls: Vec<String> = (0..100)
        .map(|i| format!(r#"<html><body>FORM 10-K Document {}</body></html>"#, i))
        .collect();

    group.bench_function("parse_100_html_docs", |b| {
        b.iter(|| {
            for html in &htmls {
                black_box(parse_html(black_box(html)).unwrap());
            }
        });
    });

    group.finish();
}

// ============================================================================
// Memory Benchmarks
// ============================================================================

fn bench_memory_usage(c: &mut Criterion) {
    let mut group = c.benchmark_group("memory");

    // Test memory allocation for large documents
    let large_doc = "<p>Lorem ipsum</p>".repeat(10000);

    group.bench_function("parse_large_html_1mb", |b| {
        b.iter(|| {
            let doc = parse_html(black_box(&large_doc)).unwrap();
            black_box(doc);
        });
    });

    group.finish();
}

// ============================================================================
// Criterion Configuration
// ============================================================================

criterion_group!(
    benches,
    bench_normalize_cik,
    bench_parse_html,
    bench_parse_json,
    bench_parse_auto,
    bench_form_type_inference,
    bench_string_operations,
    bench_throughput,
    bench_memory_usage,
);

criterion_main!(benches);
