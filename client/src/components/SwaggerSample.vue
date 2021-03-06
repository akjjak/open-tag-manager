<template>
  <div>
    <button class="btn btn-primary" @click="resetAll" v-if="!isSample">Reset</button>
    <button class="btn btn-primary" @click="autoAggregate" v-if="!isSample">Aggregate All Children</button>
    <button class="btn btn-primary" @click="showSample" v-if="!isSample">Swagger Sample</button>
    <button class="btn btn-primary" @click="isSample = false" v-if="isSample">Edit</button>
    <button class="btn btn-primary" @click="save" v-if="isSample">Save</button>
    <swagger-sample-children
      v-if="tree && tree.children.length > 0"
      :children="tree.children"
      @aggregate="aggregate" v-show="!isSample"
      @changeCheck="changeCheck"
      @partialReset="partialReset"
    ></swagger-sample-children>
    <div v-if="isSample">
      <textarea readonly :value="sampleJson" class="form-control" rows="15"></textarea>
    </div>
  </div>
</template>

<script>
  import {getPathSample} from '../lib/UrlTree'
  import SwaggerSampleChildren from './SwaggerSampleChildren'
  import _ from 'lodash'

  const findNode = function (children, id) {
    const n = _.find(children, {id})
    if (n) {
      return n
    }

    const f = children.map((c) => {
      if (c.children.length === 0) {
        return null
      }

      return findNode(c.children, id)
    })

    const r = _.reject(f, _.isEmpty)
    if (r.length > 0) {
      return r[0]
    }

    return null
  }

  export default {
    components: {SwaggerSampleChildren},
    data () {
      return {
        tree: null,
        isSample: false,
        sample: null,
        ignoredNodes: []
      }
    },
    props: {
      urlTree: {
        type: Object,
        required: true
      },
      originalUrlTree: {
        type: Object,
        required: true
      }
    },
    mounted () {
      this.reset()
    },
    computed: {
      sampleJson () {
        return JSON.stringify(this.sample, null, 2)
      }
    },
    methods: {
      reset () {
        this.tree = _.cloneDeep(this.urlTree)
        this.ignoredNodes = []
      },
      resetAll () {
        this.tree = _.cloneDeep(this.originalUrlTree)
        this.ignoredNodes = []
      },
      autoAggregate () {
        const tree = _.cloneDeep(this.tree)

        const aggregate = (child) => {
          if (child.children.length <= 0) {
            return
          }

          const newNode = {
            path: '{child}',
            id: `${child.id}/child`,
            children: null,
            level: child.level + 1,
            exists: true
          }
          const newGrandChildren = []
          child.children.forEach((c) => {
            c.children.forEach((gc) => {
              if (!_.find(newGrandChildren, {path: gc.path})) {
                newGrandChildren.push(gc)
              }
            })
          })
          newNode.children = newGrandChildren
          child.children = [newNode]
          aggregate(newNode)
        }

        for (let child of tree.children) {
          aggregate(child)
        }

        this.tree = tree
      },
      changeCheck (d) {
        if (!d.check) {
          if (!_.find(this.ignoredNodes, {id: d.node.id})) {
            this.ignoredNodes.push(d.node)
          }
        } else {
          this.ignoredNodes = _.reject(this.ignoredNodes, {id: d.node.id})
        }
      },
      partialReset (d) {
        const original = _.cloneDeep(findNode(this.originalUrlTree.children, d.id))
        if (original) {
          for (let v in this.tree.children) {
            if (this.tree.children[v].id === d.id) {
              this.tree.children[v] = original
            }
          }
        }
        this.tree = _.cloneDeep(this.tree)
      },
      aggregate (d) {
        const tree = _.cloneDeep(this.tree)
        const node = findNode(tree.children, d.node.id)
        if (!node) {
          return null
        }
        const newChildren = []
        const newNode = {
          path: `{${d.name}}`,
          id: `${node.id}/${d.name}`,
          children: null,
          level: node.level + 1,
          exists: true
        }
        newChildren.push(newNode)
        let newGrandChildren = []
        node.children.forEach((c) => {
          const node = _.find(this.ignoredNodes, {id: c.id})
          if (node) {
            newChildren.push(c)
          } else {
            c.children.forEach((gc) => {
              if (!_.find(newGrandChildren, {path: gc.path})) {
                newGrandChildren.push(gc)
              }
            })
          }
        })
        newNode.children = newGrandChildren
        node.children = newChildren
        this.tree = tree
      },
      showSample () {
        this.sample = getPathSample(this.tree)
        this.isSample = true
      },
      save () {
        this.$emit('save', {sample: this.sample})
      }
    }
  }
</script>
