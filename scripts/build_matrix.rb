#!/usr/bin/env ruby
# Build configs use a deliberately small YAML schema parsed by Ruby's standard library.
require "json"
require "open3"
require "yaml"

RUNNERS = {
  "linux-64" => "ubuntu-latest",
  "win-64" => "windows-latest",
  "osx-arm64" => "macos-latest"
}.freeze
NAME_PATTERN = /\A[a-z0-9][a-z0-9._-]*\z/

def changed_recipes
  base = ENV.fetch("BASE_SHA")
  head = ENV.fetch("HEAD_SHA")
  stdout, stderr, status = Open3.capture3("git", "diff", "--name-only", "#{base}...#{head}")
  abort "Unable to determine changed files: #{stderr}" unless status.success?

  stdout.lines.filter_map do |line|
    match = line.strip.match(/\A([^\/]+)\/build\.yaml\z/)
    match && match[1]
  end.uniq
end

def requested_recipes
  if ENV.fetch("EVENT_NAME") == "workflow_dispatch"
    [ENV.fetch("RECIPE_INPUT", "").strip.downcase]
  else
    changed_recipes
  end
end

def build_entries(recipe)
  abort "Invalid recipe name: #{recipe}" unless NAME_PATTERN.match?(recipe)

  config_path = File.join(recipe, "build.yaml")
  recipe_path = File.join(recipe, "meta.yaml")
  abort "Missing #{config_path}" unless File.file?(config_path)
  abort "Missing #{recipe_path}; conda-build needs a recipe meta.yaml" unless File.file?(recipe_path)

  config = YAML.safe_load_file(config_path, permitted_classes: [], aliases: false)
  abort "#{config_path} must contain a mapping" unless config.is_a?(Hash)
  abort "#{config_path} recipe must match its directory name" unless config["recipe"] == recipe

  platforms = config["platforms"]
  channels = config["channels"]
  abort "#{config_path} platforms must be a non-empty list" unless platforms.is_a?(Array) && !platforms.empty?
  abort "#{config_path} channels must be a non-empty list" unless channels.is_a?(Array) && !channels.empty?
  abort "#{config_path} contains an unsupported platform" unless (platforms - RUNNERS.keys).empty?
  abort "#{config_path} channels must be non-empty strings" unless channels.all? { |channel| channel.is_a?(String) && !channel.empty? }

  platforms.map do |platform|
    abort "#{config_path} contains an unsupported platform" unless RUNNERS.key?(platform)

    {
      recipe: recipe,
      platform: platform,
      runner: RUNNERS.fetch(platform),
      channels: channels
    }
  end
end

recipes = requested_recipes
abort "No recipe build.yaml was selected or changed" if recipes.empty?

entries = recipes.flat_map { |recipe| build_entries(recipe) }
abort "No platform builds were configured" if entries.empty?

output = { include: entries }
File.open(ENV.fetch("GITHUB_OUTPUT"), "a") do |file|
  file.puts("matrix=#{JSON.generate(output)}")
end
